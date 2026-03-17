# Plan: Gene tools redesign — `gene_overview` (new) + `get_gene_details` (simplify)

Add a new `gene_overview` tool for batch gene routing (identity + data
availability signals from pre-computed Gene node properties). Simplify
`get_gene_details` to a flat `g {.*}` dump without nested sub-objects.
Delete `build_get_gene_details_homologs`.

See `gene_tools_three_tier.md` for design rationale and discussion.

## Status / Prerequisites

- [x] KG: `annotation_types` pre-computed on Gene nodes
- [x] KG: `expression_edge_count` + `significant_expression_count` pre-computed
- [x] KG: `closest_ortholog_group_size` + `closest_ortholog_genera` pre-computed
- [x] KG: `gene_synonyms`, `alternative_locus_tags`, `old_locus_tags` removed
- [x] KG rebuilt and verified (PMM1428, EZ55_00275 spot-checked)

## Out of Scope

- File I/O (`output_file`/`input_file` parameters) — separate plan
- Changes to `resolve_gene`, `search_genes`, or ontology tools
- Protein sub-object — dropped; use `run_cypher` for protein-level fields

---

## Tool Signature: `gene_overview`

```python
@mcp.tool()
def gene_overview(
    ctx: Context,
    gene_ids: list[str],
    limit: int = 50,
) -> str:
    """Get an overview of one or more genes: identity and data availability.

    Use this after resolve_gene, search_genes, genes_by_ontology, or
    get_homologs to understand what each gene is and what follow-up data
    exists.

    Returns one row per gene with routing signals:
    - annotation_types: which ontology types have annotations
      → use gene_ontology_terms with the relevant type
    - expression_edge_count + significant_expression_count: whether
      expression data exists and how much is significant
      → use query_expression
    - closest_ortholog_group_size + closest_ortholog_genera: whether
      orthologs exist and in which genera
      → use get_homologs for full membership

    Args:
        gene_ids: List of gene locus_tags.
                  Use resolve_gene to find locus_tags from other identifiers.
        limit: Max genes to return (default 50).
    """
```

**Return columns:**
`locus_tag`, `gene_name`, `product`, `gene_summary`, `gene_category`,
`annotation_quality`, `organism_strain`, `annotation_types`,
`expression_edge_count`, `significant_expression_count`,
`closest_ortholog_group_size`, `closest_ortholog_genera`

---

## Tool Signature: `get_gene_details` (simplified)

```python
@mcp.tool()
def get_gene_details(
    ctx: Context,
    gene_id: str,
) -> str:
    """Get all properties for a gene.

    This is a deep-dive tool — use gene_overview for the common case.
    Returns all Gene node properties including sparse fields
    (catalytic_activities, transporter_classification, cazy_ids, etc.).

    For organism taxonomy, use list_organisms. For homologs, use
    get_homologs. For ontology annotations, use gene_ontology_terms.
    For expression data, use query_expression.

    Args:
        gene_id: Gene locus_tag (e.g. "PMM0001", "sync_0001").
    """
```

**Return columns:** All Gene node properties via `g {.*}` (~26 properties).
No nested sub-objects (`_protein`, `_organism`, `_ortholog_groups`, `_homologs`).

---

## KG-side Changes

- [x] ~~K1: Add `annotation_types` list property to Gene nodes~~
- [x] ~~K2: Add `expression_edge_count` + `significant_expression_count` int properties~~
- [x] ~~K3: Add `closest_ortholog_group_size` + `closest_ortholog_genera` properties~~
- [x] ~~K4: Remove `gene_synonyms`, `alternative_locus_tags`, `old_locus_tags`~~
- [x] ~~K5: Rebuild KG~~

All KG changes done and verified.

## Implementation Order

| Order | Change | Where | Status |
|-------|--------|-------|--------|
| 1a | Add `build_gene_overview` query builder | `queries_lib.py` | TODO |
| 1b | Simplify `build_get_gene_details_main` → `build_get_gene_details` | `queries_lib.py` | TODO |
| 1c | Delete `build_get_gene_details_homologs` | `queries_lib.py` | TODO |
| 2a | Add `gene_overview` tool wrapper | `tools.py` | TODO |
| 2b | Update `get_gene_details` tool wrapper (simplified) | `tools.py` | TODO |
| 3a | Update tests | `tests/` | TODO |
| 3b | Update docs | `CLAUDE.md`, `README.md`, `AGENT.md`, `docs/testplans/` | TODO |
| 4 | Code review | all changes | TODO |

Steps 1a-1c are independent. Steps 2a-2b depend on their query builders.
Steps 3a-3b can run in parallel after 2a-2b. Step 4 after all.

## Agent Assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1a | **query-builder** | Add `build_gene_overview` to `queries_lib.py` | — |
| 1b | **query-builder** | Rename `build_get_gene_details_main` → `build_get_gene_details`, simplify to `g {.*}` | — |
| 1c | **query-builder** | Delete `build_get_gene_details_homologs` | — |
| 2a | **tool-wrapper** | Add `gene_overview` tool to `tools.py`, register in MCP server | 1a |
| 2b | **tool-wrapper** | Simplify `get_gene_details` wrapper (single query, no homologs merge), remove `build_get_gene_details_homologs` import | 1b, 1c |
| 3a | **test-updater** | Update all tests: unit, integration, evals, regression | 2a, 2b |
| 3b | **doc-updater** | Update `CLAUDE.md`, `README.md`, `AGENT.md`, `docs/testplans/testplan.md` | 2a, 2b |
| 4 | **code-reviewer** | Review all changes against this plan | 3a, 3b |

---

## Query Builders

**File:** `multiomics_explorer/kg/queries_lib.py`

### `build_gene_overview` (new)

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.gene_summary AS gene_summary,
       g.gene_category AS gene_category, g.annotation_quality AS annotation_quality,
       g.organism_strain AS organism_strain,
       g.annotation_types AS annotation_types,
       g.expression_edge_count AS expression_edge_count,
       g.significant_expression_count AS significant_expression_count,
       g.closest_ortholog_group_size AS closest_ortholog_group_size,
       g.closest_ortholog_genera AS closest_ortholog_genera
ORDER BY g.locus_tag
LIMIT $limit
```

**Strategy:** All routing signals are pre-computed Gene node properties.
No OPTIONAL MATCHes, no graph traversal beyond index lookup. Fast for
batches up to 50 genes.

**Signature:**
```python
def build_gene_overview(
    *, locus_tags: list[str], limit: int = 50,
) -> tuple[str, dict]:
```

### `build_get_gene_details` (renamed + simplified)

Rename from `build_get_gene_details_main`. Drop `_protein`, `_organism`,
`_ortholog_groups` sub-objects.

```cypher
MATCH (g:Gene {locus_tag: $lt})
RETURN g {.*} AS gene
```

**Strategy:** Flat dump of all Gene node properties. Since KG cleanup
reduced Gene from ~50 to ~26 properties, `g {.*}` is reasonable.
No joins needed — organism info is on `organism_strain`, homologs are
in `get_homologs`, ontology annotations are in `gene_ontology_terms`.

**Signature:**
```python
def build_get_gene_details(*, gene_id: str) -> tuple[str, dict]:
```

### `build_get_gene_details_homologs` — DELETE

No longer needed. Homolog data is served by `get_homologs` tool
(which uses `build_get_homologs_groups` + `build_get_homologs_members`).

---

## Tool Wrapper Logic

**File:** `multiomics_explorer/mcp_server/tools.py`

### `gene_overview` wrapper

Straightforward query-and-format. No post-query logic needed since all
signals are pre-computed on Gene nodes.

```python
def gene_overview(ctx: Context, gene_ids: list[str], limit: int = 50) -> str:
    conn = _conn(ctx)
    cypher, params = build_gene_overview(locus_tags=gene_ids, limit=limit)
    rows = conn.execute_query(cypher, **params)
    if not rows:
        return "No genes found for the given locus_tags."
    response = _fmt(rows)
    return _with_query(response, cypher, params, ctx)
```

### `get_gene_details` wrapper (simplified)

Remove the two-query pattern (main + homologs). Single query, single result.

```python
def get_gene_details(ctx: Context, gene_id: str) -> str:
    conn = _conn(ctx)
    cypher, params = build_get_gene_details(gene_id=gene_id)
    results = conn.execute_query(cypher, **params)
    if not results or results[0]["gene"] is None:
        return f"Gene '{gene_id}' not found."
    response = _fmt([results[0]["gene"]])
    return _with_query(response, cypher, params, ctx)
```

**Changes from current:**
- Remove `build_get_gene_details_homologs` import (moved from step 1c)
- Remove second query call and `_homologs` merge
- Remove multi-query debug block — `_with_query` handles single-query debug

---

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**

Update `TestBuildGetGeneDetails`:
- [ ] Rename test class to match new function names
- [ ] `test_gene_overview_query` — UNWIND present, returns all 12 expected columns,
      `$locus_tags` and `$limit` in params
- [ ] `test_gene_overview_columns` — verify all column names in RETURN clause:
      `locus_tag`, `gene_name`, `product`, `gene_summary`, `gene_category`,
      `annotation_quality`, `organism_strain`, `annotation_types`,
      `expression_edge_count`, `significant_expression_count`,
      `closest_ortholog_group_size`, `closest_ortholog_genera`
- [ ] `test_get_gene_details_simplified` — `g {.*}` in RETURN, no
      `Gene_encodes_protein`, no `Gene_belongs_to_organism`, no
      `Gene_in_ortholog_group`
- [ ] `test_build_get_gene_details_homologs_deleted` — verify function
      no longer importable from `queries_lib`
- [ ] Remove `test_homologs_query` and `test_main_query_ortholog_groups`

**`tests/unit/test_tool_wrappers.py`:**

Update `EXPECTED_TOOLS` list (add `"gene_overview"`, keep `"get_gene_details"`):
- [ ] Add `"gene_overview"` to `EXPECTED_TOOLS` (13 → 14 tools)

Add `TestGeneOverviewWrapper`:
- [ ] `test_not_found_empty_results` — empty query result returns "No genes found"
- [ ] `test_returns_json_list` — mock rows returned as JSON list
- [ ] `test_limit_passed_to_query` — verify limit param forwarded

Update `TestGetGeneDetailsWrapper`:
- [ ] `test_not_found_message` — keep, same behavior
- [ ] `test_not_found_empty_results` — keep, same behavior
- [ ] `test_single_query_no_homologs` — replace `test_assembles_homologs_into_result`.
      Verify single `execute_query` call (not two), no `_homologs` key in result.
- [ ] Remove `test_assembles_homologs_into_result`

**`tests/unit/test_tool_correctness.py`:**

Update `TestGetGeneDetailsCorrectness`:
- [ ] `test_well_annotated_prochlorococcus` — remove assertions on `_protein`,
      `_organism`, `_ortholog_groups`, `_homologs`. Assert flat `g {.*}` structure.
      Single `execute_query` call (not two).
- [ ] `test_alteromonas_gene_eggnog_only` — same: remove nested sub-object
      assertions, verify flat return, single query call.
- [ ] Remove `test_homologs_merged_from_different_organisms` — no longer applicable.

Add `TestGeneOverviewCorrectness`:
- [ ] `test_single_gene_overview` — mock single gene row with all 12 columns,
      verify JSON output structure.
- [ ] `test_batch_overview` — mock multiple gene rows, verify all returned.
- [ ] `test_annotation_types_preserved` — list field preserved in JSON output.

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

Update `TestGetGeneDetailsCorrectnessKG`:
- [ ] `test_well_annotated_prochlorococcus` — update to expect flat `g {.*}`
      return. Remove assertions on `_protein`, `_organism`, `_ortholog_groups`.
      Assert `locus_tag`, `gene_name`, `product`, `organism_strain` present.
- [ ] `test_alteromonas_has_eggnog_groups` — remove (no `_ortholog_groups` in return).
      Replace with `test_alteromonas_gene` — verify flat return with
      `organism_strain` containing "Alteromonas".
- [ ] Remove `test_homologs_exist_for_pmm0001` — tested by `get_homologs` tool.

Add `TestGeneOverviewCorrectnessKG`:
- [ ] `test_single_gene_pro` — PMM1428: `annotation_types` includes
      `["go_mf", "pfam", "cog_category", "tigr_role"]`, `expression_edge_count` = 36,
      `significant_expression_count` = 5, `closest_ortholog_group_size` = 9,
      `closest_ortholog_genera` = `["Prochlorococcus", "Synechococcus"]`
- [ ] `test_single_gene_alt` — EZ55_00275: `annotation_types` = [],
      `expression_edge_count` = 0, `closest_ortholog_group_size` = 1
- [ ] `test_batch_mixed_organisms` — [PMM1428, EZ55_00275]: returns 2 rows,
      each with correct organism_strain
- [ ] `test_nonexistent_gene_excluded` — [PMM1428, FAKE_GENE]: returns 1 row
      (only PMM1428)

### Eval cases (`tests/evals/cases.yaml`)

Update existing:
```yaml
# Replace gene_details_has_organism
- id: gene_details_flat_return
  tool: get_gene_details
  desc: Gene details returns flat g{.*} properties
  params:
    gene_id: PMM0001
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain, gene_category]
```

Add new:
```yaml
# ── Gene overview ──────────────────────────────────────────

- id: gene_overview_single_pro
  tool: gene_overview
  desc: Single Prochlorococcus gene overview with routing signals
  params:
    gene_ids: ["PMM1428"]
  expect:
    min_rows: 1
    columns: [locus_tag, gene_summary, annotation_types,
              expression_edge_count, significant_expression_count,
              closest_ortholog_group_size, closest_ortholog_genera]

- id: gene_overview_single_alt
  tool: gene_overview
  desc: Single Alteromonas gene overview
  params:
    gene_ids: ["EZ55_00275"]
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain]

- id: gene_overview_batch
  tool: gene_overview
  desc: Batch overview for Pro + Alt genes
  params:
    gene_ids: ["PMM1428", "EZ55_00275"]
  expect:
    min_rows: 2
    columns: [locus_tag, gene_summary, annotation_types]
```

Update corner cases section:
```yaml
# Update existing gene_details corner cases
- id: gene_details_alteromonas
  tool: get_gene_details
  desc: Alteromonas gene details flat return
  params:
    gene_id: ALT831_RS00180
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain]

- id: gene_details_synechococcus
  tool: get_gene_details
  desc: Synechococcus gene details flat return
  params:
    gene_id: SYNW0305
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain]
```

### Regression tests (`tests/regression/`)

Update `TOOL_BUILDERS` in `test_regression.py`:
- Replace `build_get_gene_details_main` import with `build_get_gene_details`
- Add `build_gene_overview` import
- Add entry: `"gene_overview": partial(build_gene_overview, locus_tags=["PMM1428"])`
- Update entry: `"get_gene_details": build_get_gene_details`

Add regression cases to `tests/evals/cases.yaml` (shared with evals):
```yaml
- id: gene_overview_regression_pro
  tool: gene_overview
  desc: Gene overview regression baseline for Pro gene
  params:
    gene_ids: ["PMM1428"]

- id: gene_overview_regression_alt
  tool: gene_overview
  desc: Gene overview regression baseline for Alt gene
  params:
    gene_ids: ["EZ55_00275"]
```

After implementation, regenerate baselines:
```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```

Note: `gene_overview` eval/regression cases need special handling in
`run_case()` / `TOOL_BUILDERS` since the query builder takes `locus_tags`
(list) not `gene_id` (string). Add a `gene_overview` entry to `run_case()`
or handle via partial.

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add `gene_overview` to MCP Tools table. Update `get_gene_details` description (remove "protein, organism, ortholog groups"). |
| `README.md` | Add `gene_overview` to MCP tools list. Update `get_gene_details` description. Bump tool count (13 → 14). |
| `AGENT.md` | Add `gene_overview` to tools table. Update `get_gene_details` row. |
| `docs/testplans/testplan.md` | Add test plan section for `gene_overview`. Update `get_gene_details` test section. |
