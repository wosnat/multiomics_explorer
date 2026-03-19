# Plan: `query_expression` — redefinition + expression cleanup

Major rewrite of `query_expression` and removal of `compare_conditions`.
Also updates `list_filter_values` for the new schema and cleans up old
expression constants/builders.

## Status / Prerequisites

- [ ] KG change: Experiment node redesign complete and rebuilt
- [ ] KG change: `Changes_expression_of` edges with time_point_order,
  time_point_hours, significant, rank_by_effect
- [ ] Explorer: `list_experiments` implemented (provides experiment_ids)

## Out of Scope

- `list_publications` — separate plan (`list_publications.md`)
- `list_experiments` — separate plan (`list_experiments.md`)
- Phase 2 temporal profiling (`query_temporal_profile`) — deferred
- `gene_overview` routing signal updates — deferred to implementation

---

## Tool Signature

```python
@mcp.tool()
def query_expression(
    ctx: Context,
    experiment_id: str | None = None,
    gene_ids: list[str] | None = None,
    include_orthologs: bool = False,
    organism: str | None = None,
    condition_type: str | None = None,
    time_points: list[str] | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    significant_only: bool | None = None,
    limit: int = 100,
) -> str:
    """Query differential expression results from the knowledge graph.

    Two modes:

    **Experiment-centric** (provide experiment_id): Returns significant genes
    for a specific experiment. Use list_experiments to find experiment IDs.
    Default: significant_only=True.

    **Gene-centric** (provide gene_ids): Returns expression results for
    specific genes across all experiments. Shows which conditions affect
    these genes. Default: significant_only=False (absence of response is
    informative).

    At least one of experiment_id or gene_ids must be provided.

    Args:
        experiment_id: Experiment ID from list_experiments.
        gene_ids: List of gene locus_tags (e.g. ["PMM0001", "PMM0120"]).
        include_orthologs: Expand gene_ids to include orthologs via
            OrthologGroup. Only in gene-centric mode (ignored when
            experiment_id provided). Warns if expanded orthologs have
            no expression data in other strains.
        organism: Filter by organism strain (CONTAINS). For gene-centric
            mode — narrows which experiments to search.
        condition_type: Filter by experiment type (exact match on
            treatment_type). E.g. "nitrogen_stress", "coculture".
            Use list_filter_values for valid values.
        time_points: Filter to specific time points within a time-course
            experiment. E.g. ["1h", "24h"]. Matches on time_point label.
        direction: Filter by "up" or "down" regulation.
        min_log2fc: Minimum absolute log2 fold change.
        max_pvalue: Maximum adjusted p-value.
        significant_only: Default depends on mode — True for experiment-
            centric, False for gene-centric. Override explicitly if needed.
        limit: Max genes returned (default 100). For time courses, limit
            is per-gene — 100 genes × N time points. Rows ordered by
            absolute fold change.
    """
```

**Return columns:**
`gene`, `product`, `organism_strain`, `experiment_id`, `experiment_name`,
`publication_doi`, `condition_type`, `time_point`, `time_point_order`,
`direction`, `log2fc`, `padj`, `rank_by_effect`.

When `include_orthologs=True`, also: `ortholog_group`, `query_gene`.

---

## KG-side Changes

- [ ] K1: Experiment node + `Changes_expression_of` edges (KG plan)
- [ ] K2: `rank_by_effect` computed post-import

## Implementation Order

| Order | Change | Where | Status |
|-------|--------|-------|--------|
| 1 | Experiment node + edges + rank_by_effect | KG | pending |
| 2 | Remove `DIRECT_EXPR_RELS` constant, `build_query_expression`, `build_compare_conditions` from `queries_lib.py` | Explorer | this file |
| 3 | Add `build_query_expression_v2` to `queries_lib.py` (two query modes) | Explorer | this file |
| 4 | Rewrite `query_expression` tool in `tools.py`, remove `compare_conditions` | Explorer | this file |
| 5 | Update `list_filter_values` condition_types query + add omics_types | Explorer | this file |
| 6 | Tests, docs, cleanup | Explorer | this file |

Steps 2+3 can be one commit. Step 4 depends on 3. Step 5 can parallel 4.

## Agent Assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1 | **query-builder** | Remove old builders, add `build_query_expression_v2` (both modes) to `queries_lib.py` | KG rebuild |
| 2 | **tool-wrapper** | Rewrite `query_expression`, remove `compare_conditions`, update `list_filter_values` in `tools.py` | query-builder |
| 3a | **test-updater** | Update all expression tests, remove compare_conditions tests, add new tests | tool-wrapper |
| 3b | **doc-updater** | Update `CLAUDE.md`, `README.md`, `AGENT.md`, `docs/testplans/testplan.md` | tool-wrapper |
| 4 | **code-reviewer** | Review all changes, run unit tests, grep for stale refs to old edge types | test-updater, doc-updater |

---

## Query Builders

**Files:** `queries_lib.py`

### Remove

- `DIRECT_EXPR_RELS` constant (line 78)
- `build_query_expression` (lines 170–237)
- `build_compare_conditions` (lines 240–285)
- `build_list_condition_types` (lines 383–389)

### Add: `build_query_expression` (new)

Two query modes — experiment-centric and gene-centric. Both query through
Experiment → Changes_expression_of → Gene.

#### Experiment-centric mode (has experiment_id)

```cypher
MATCH (e:Experiment {id: $exp_id})-[r:Changes_expression_of]->(g:Gene)
{where_block}
WITH g, r, e
ORDER BY abs(r.log2_fold_change) DESC
WITH DISTINCT g, collect(r) AS edges, e
LIMIT $limit
UNWIND edges AS r
MATCH (p:Publication)-[:Has_experiment]->(e)
RETURN g.locus_tag AS gene,
       g.product AS product,
       g.organism_strain AS organism_strain,
       e.id AS experiment_id,
       e.name AS experiment_name,
       p.doi AS publication_doi,
       e.treatment_type AS condition_type,
       r.time_point AS time_point,
       r.time_point_order AS time_point_order,
       r.expression_direction AS direction,
       r.log2_fold_change AS log2fc,
       r.adjusted_p_value AS padj,
       r.rank_by_effect AS rank_by_effect
ORDER BY abs(r.log2_fold_change) DESC, g.locus_tag, r.time_point_order
```

**Per-gene limit strategy:** The query first collects all edges per gene,
then applies LIMIT on distinct genes, then unwinds to get all time points
for those genes. This means `limit=100` returns at most 100 genes, each
with all their time points.

#### Gene-centric mode (has gene_ids, no experiment_id)

```cypher
MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)
WHERE g.locus_tag IN $gene_ids
{extra_where}
MATCH (p:Publication)-[:Has_experiment]->(e)
RETURN g.locus_tag AS gene,
       g.product AS product,
       g.organism_strain AS organism_strain,
       e.id AS experiment_id,
       e.name AS experiment_name,
       p.doi AS publication_doi,
       e.treatment_type AS condition_type,
       r.time_point AS time_point,
       r.time_point_order AS time_point_order,
       r.expression_direction AS direction,
       r.log2_fold_change AS log2fc,
       r.adjusted_p_value AS padj,
       r.rank_by_effect AS rank_by_effect
ORDER BY g.locus_tag, e.id, r.time_point_order
LIMIT $limit
```

Gene-centric LIMIT is per-row (not per-gene) because the gene list is
already bounded by the caller. Results ordered by gene then experiment
for easy comparison across conditions.

#### WHERE clause construction (shared)

```python
where_clauses: list[str] = []
params: dict = {}

# Mode detection
if experiment_id:
    params["exp_id"] = experiment_id

if gene_ids:
    params["gene_ids"] = gene_ids

# Determine significant_only default
if significant_only is None:
    significant_only = experiment_id is not None and gene_ids is None

if significant_only:
    where_clauses.append("r.significant = 'significant'")

if direction:
    where_clauses.append("r.expression_direction = $dir")
    params["dir"] = direction.lower()

if min_log2fc is not None:
    where_clauses.append("abs(r.log2_fold_change) >= $min_fc")
    params["min_fc"] = min_log2fc

if max_pvalue is not None:
    where_clauses.append(
        "r.adjusted_p_value IS NOT NULL AND r.adjusted_p_value <= $max_pv"
    )
    params["max_pv"] = max_pvalue

if time_points:
    where_clauses.append("r.time_point IN $tps")
    params["tps"] = time_points

# Gene-centric filters (only when no experiment_id)
if not experiment_id:
    if organism:
        where_clauses.append("e.organism_strain CONTAINS $org")
        params["org"] = organism

    if condition_type:
        where_clauses.append("e.treatment_type = $ctype")
        params["ctype"] = condition_type

params["limit"] = limit
```

**Function signature:**

```python
def build_query_expression(
    *,
    experiment_id: str | None = None,
    gene_ids: list[str] | None = None,
    organism: str | None = None,
    condition_type: str | None = None,
    time_points: list[str] | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    significant_only: bool = True,
    limit: int = 100,
) -> tuple[str, dict]:
```

Note: `significant_only` default resolution happens in the tool wrapper,
not the builder. The builder always receives an explicit bool.

### Add: `build_list_condition_types` (updated)

```cypher
MATCH (e:Experiment)
RETURN DISTINCT e.treatment_type AS condition_type, count(e) AS cnt
ORDER BY cnt DESC
```

Replaces the old query that read from EnvironmentalCondition nodes.

### Add: `build_list_omics_types` (new)

```cypher
MATCH (e:Experiment)
RETURN DISTINCT e.omics_type AS omics_type, count(e) AS cnt
ORDER BY cnt DESC
```

---

## Tool Wrapper Logic

**Files:** `tools.py`

### `query_expression` — rewrite

Non-trivial wrapper logic:

1. **Input validation** — at least one of experiment_id or gene_ids
2. **significant_only default** — infer from mode
3. **include_orthologs expansion** — gene-centric only, calls get_homologs
4. **Ortholog warning** — detect strains with no expression data
5. **Format response**

```python
@mcp.tool()
def query_expression(ctx, experiment_id=None, gene_ids=None,
                     include_orthologs=False, organism=None,
                     condition_type=None, time_points=None,
                     direction=None, min_log2fc=None, max_pvalue=None,
                     significant_only=None, limit=100):
    if not experiment_id and not gene_ids:
        return "Error: provide at least one of experiment_id or gene_ids."

    # Resolve significant_only default from mode
    if significant_only is None:
        significant_only = (experiment_id is not None and gene_ids is None)

    # Ortholog expansion (gene-centric only)
    query_gene_map = {}  # expanded_locus_tag → original_query_gene
    ortholog_warning = None
    if include_orthologs and gene_ids and not experiment_id:
        expanded_ids, query_gene_map, ortholog_warning = (
            _expand_orthologs(ctx, gene_ids)
        )
        gene_ids = expanded_ids

    conn = _conn(ctx)
    cypher, params = build_query_expression(
        experiment_id=experiment_id, gene_ids=gene_ids,
        organism=organism, condition_type=condition_type,
        time_points=time_points, direction=direction,
        min_log2fc=min_log2fc, max_pvalue=max_pvalue,
        significant_only=significant_only, limit=limit,
    )
    results = conn.execute_query(cypher, **params)

    # Add ortholog columns if expanded
    if query_gene_map:
        for row in results:
            row["query_gene"] = query_gene_map.get(row["gene"], row["gene"])
            # ortholog_group could be added via a join query or cached

    if not results:
        msg = "No expression data found for the given filters."
        if ortholog_warning:
            msg += f"\n\n{ortholog_warning}"
        return _with_query(msg, cypher, params, ctx)

    response = _fmt(results)
    if ortholog_warning:
        response = f"{ortholog_warning}\n\n{response}"
    return _with_query(response, cypher, params, ctx)
```

### `_expand_orthologs` helper

```python
def _expand_orthologs(ctx, gene_ids: list[str]):
    """Expand gene_ids to include orthologs. Returns:
    - expanded_ids: full list including orthologs
    - query_gene_map: {expanded_id: original_query_gene}
    - warning: str or None if some strains have no expression data
    """
    from .tools import get_homologs  # or use build_get_homologs_groups

    all_ids = list(gene_ids)
    query_gene_map = {g: g for g in gene_ids}

    for gene_id in gene_ids:
        conn = _conn(ctx)
        # Get orthologs — reuse existing homolog query logic
        cypher, params = build_get_homologs_groups(gene_id=gene_id)
        groups = conn.execute_query(cypher, **params)
        for group in groups:
            members_cypher, members_params = build_get_homologs_members(
                group_id=group["group_id"]
            )
            members = conn.execute_query(members_cypher, **members_params)
            for member in members:
                lt = member["locus_tag"]
                if lt not in query_gene_map:
                    all_ids.append(lt)
                    query_gene_map[lt] = gene_id

    # Check which expanded strains have expression data
    expanded_strains = set()
    for lt in all_ids:
        if lt not in gene_ids:
            # Extract strain from locus_tag prefix or query
            pass  # implementation detail

    # Generate warning for strains with no experiments
    # (check against Experiment.organism_strain values)
    warning = None
    # ... build warning string if needed

    return all_ids, query_gene_map, warning
```

The exact implementation of strain-checking and warning generation is an
implementation detail. The key contract: expanded IDs are returned, and
a warning string is generated when some strains lack expression experiments.

### `compare_conditions` — remove

Delete the tool function and its `@mcp.tool()` decorator entirely.

### `list_filter_values` — update

Update the condition_types query to use Experiment instead of
EnvironmentalCondition. Add omics_types.

```python
@mcp.tool()
def list_filter_values(ctx, filter_name):
    # ...existing gene_categories handling...

    if filter_name == "condition_types":
        cypher, params = build_list_condition_types()  # updated query
        # ...

    if filter_name == "omics_types":
        cypher, params = build_list_omics_types()  # new query
        # ...
```

---

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**

Remove:
- [ ] `TestBuildQueryExpression` (old class)
- [ ] `TestBuildCompareConditions` (old class)

Add:
- [ ] `TestBuildQueryExpressionV2.test_experiment_centric` — has
  Experiment {id: $exp_id} match, Changes_expression_of edge
- [ ] `test_gene_centric` — has g.locus_tag IN $gene_ids
- [ ] `test_significant_only_true` — WHERE has r.significant = 'significant'
- [ ] `test_significant_only_false` — no significant filter in WHERE
- [ ] `test_direction_lowercased` — params["dir"] is lowercase
- [ ] `test_min_log2fc` — WHERE has abs(r.log2_fold_change) >= $min_fc
- [ ] `test_max_pvalue` — WHERE has adjusted_p_value check
- [ ] `test_time_points_filter` — WHERE has r.time_point IN $tps
- [ ] `test_organism_filter_gene_centric` — WHERE has organism_strain CONTAINS
- [ ] `test_condition_type_maps_to_treatment_type` — WHERE has
  e.treatment_type = $ctype (not condition_type)
- [ ] `test_no_ortholog_edges` — Cypher does NOT contain
  Gene_in_ortholog_group or OrthologGroup
- [ ] `test_experiment_centric_limit_per_gene` — LIMIT on distinct genes,
  not on rows

**`tests/unit/test_tool_wrappers.py`:**

Remove:
- [ ] `TestQueryExpressionWrapper` (old class)
- [ ] `TestCompareConditionsWrapper` (old class)

Add:
- [ ] `TestQueryExpressionWrapperV2.test_no_anchor_error` — returns error
  when neither experiment_id nor gene_ids provided
- [ ] `test_experiment_centric_sig_default` — significant_only defaults True
  when experiment_id provided
- [ ] `test_gene_centric_sig_default` — significant_only defaults False
  when gene_ids provided
- [ ] `test_include_orthologs_ignored_with_experiment` — include_orthologs
  silently ignored when experiment_id provided
- [ ] `test_empty_results` — returns "No expression data found."
- [ ] `test_ortholog_warning_included` — warning text present when orthologs
  expand to strains without data
- [ ] `test_query_gene_column_added` — when include_orthologs, results have
  query_gene column
- [ ] Tool registration count updated (compare_conditions removed, net -1
  or same if list_publications/list_experiments added in same commit)

**`tests/unit/test_tool_correctness.py`** (if applicable):
- [ ] Update any existing expression correctness tests

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

Experiment-centric:
- [ ] `experiment_id` for known experiment → returns genes with expression data
- [ ] Significant-only default → only significant rows
- [ ] `direction="up"` → only upregulated genes
- [ ] `min_log2fc=2.0` → all rows have |log2fc| >= 2.0
- [ ] Time-course experiment → time_point and time_point_order populated
- [ ] `time_points=["1h"]` → filters to that time point only
- [ ] `limit=5` → at most 5 distinct genes (but may have multiple time points)
- [ ] `rank_by_effect` is populated and rank 1 has largest |log2fc|

Gene-centric:
- [ ] `gene_ids=["PMM0001"]` → returns results across multiple experiments
- [ ] `gene_ids=["PMM0001"], significant_only=False` → includes
  non-significant results
- [ ] `gene_ids=["PMM0001"], condition_type="coculture"` → only coculture
  experiments
- [ ] `gene_ids=["PMM0001"], include_orthologs=True` → returns orthologs
  from other strains (if data exists)
- [ ] `include_orthologs=True` with `experiment_id` → orthologs ignored

Validation:
- [ ] No results for nonexistent experiment_id → error message
- [ ] No results for nonexistent gene_id → empty response
- [ ] Return columns match spec

### Eval cases (`tests/evals/cases.yaml`)

Remove old:
- `expression_by_gene`
- `expression_by_organism`
- `expression_coculture_up`
- `compare_conditions_med4`

Add new:
```yaml
- id: query_expression_experiment_centric
  tool: query_expression
  desc: Experiment-centric returns significant genes
  params:
    experiment_id: "<known_experiment_id>"  # fill after KG rebuild
  expect:
    min_rows: 10
    columns: [gene, product, experiment_id, experiment_name, direction,
              log2fc, padj, rank_by_effect]

- id: query_expression_experiment_direction
  tool: query_expression
  desc: Filter by direction within experiment
  params:
    experiment_id: "<known_experiment_id>"
    direction: "up"
  expect:
    min_rows: 5
    columns: [gene, direction, log2fc]
    contains:
      direction: "up"

- id: query_expression_gene_centric
  tool: query_expression
  desc: Gene across all experiments
  params:
    gene_ids: ["PMM0001"]
  expect:
    min_rows: 1
    columns: [gene, experiment_id, experiment_name, condition_type,
              direction, log2fc, padj]
    contains:
      gene: "PMM0001"

- id: query_expression_gene_condition
  tool: query_expression
  desc: Gene filtered by condition type
  params:
    gene_ids: ["PMM0001"]
    condition_type: "coculture"
  expect:
    min_rows: 1
    columns: [gene, condition_type]
    contains:
      condition_type: "coculture"

- id: query_expression_time_course
  tool: query_expression
  desc: Time-course experiment returns time points
  params:
    experiment_id: "<known_timecourse_experiment_id>"
    limit: 5
  expect:
    min_rows: 5
    columns: [gene, time_point, time_point_order, log2fc]

- id: query_expression_min_fc
  tool: query_expression
  desc: Minimum fold-change filter
  params:
    experiment_id: "<known_experiment_id>"
    min_log2fc: 2.0
  expect:
    min_rows: 1
    columns: [gene, log2fc]
```

### Regression tests

```yaml
- id: query_expression_experiment
  tool: query_expression
  desc: Snapshot experiment-centric results
  params:
    experiment_id: "<known_experiment_id>"
    limit: 10

- id: query_expression_gene
  tool: query_expression
  desc: Snapshot gene-centric results
  params:
    gene_ids: ["PMM0001"]
```

After implementation:
```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```

---

## Cleanup: remove stale references

After implementation, grep for and remove all references to:

- `DIRECT_EXPR_RELS`
- `build_query_expression` (old version)
- `build_compare_conditions`
- `compare_conditions` (tool)
- `Condition_changes_expression_of`
- `Coculture_changes_expression_of`
- `Published_expression_data_about`
- `EnvironmentalCondition` (in expression-related code)
- `edge_type` return column (old query_expression returned this)

```bash
grep -rn "DIRECT_EXPR_RELS\|build_compare_conditions\|compare_conditions\|Condition_changes_expression_of\|Coculture_changes_expression_of\|Published_expression_data_about" multiomics_explorer/ tests/
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Update `query_expression` row in MCP Tools table (new signature, two modes). Remove `compare_conditions` row. Update `list_filter_values` description (new omics_types filter). |
| `README.md` | Update query_expression description. Remove compare_conditions. Update tool count. |
| `AGENT.md` | Same updates as CLAUDE.md tools table. |
| `docs/testplans/testplan.md` | Replace expression test plan section. Remove compare_conditions section. |
