# Utility reference docs + gene_response_profile groups_tested_not_responded

**Date:** 2026-03-31
**Source spec:** `multiomics_research/docs/superpowers/specs/2026-03-31-explorer-utils-docs-and-response-profile-change.md`

Three independent deliverables. Part 1 (docs) can ship first.
Part 2 (response_profile change) depends on Cypher verification.
Part 3 (DataFrame utilities) is independent of Parts 1-2.

---

## Part 1: Analysis function reference docs

### Goal

Claude doesn't know the `response_matrix` and `gene_set_compare`
utilities exist. Add reference docs so they surface as MCP resources,
matching the existing tool guide pattern.

### Deliverables

1. **New directory:** `skills/multiomics-kg-guide/references/analysis/`

2. **Two reference files:**
   - `references/analysis/response_matrix.md`
   - `references/analysis/gene_set_compare.md`

3. **Format:** Same structure as tool guides:
   - What it does
   - Parameters (table)
   - Response format (DataFrame columns / dict keys with types)
   - Few-shot examples (2–3 realistic workflows as runnable Python)
   - Chaining patterns (how it connects to MCP tools / other utils)
   - Common mistakes
   - Reference script example (short end-to-end runnable snippet)

4. **MCP resource registration:** New handler in `server.py`:
   ```python
   @mcp.resource("docs://analysis/{name}")
   def analysis_docs(name: str) -> str:
       path = _ANALYSIS_DOCS_DIR / f"{name}.md"
       if not path.exists():
           return f"No documentation found for analysis function '{name}'."
       return path.read_text()
   ```

5. **MCP server instructions:** Update the server docstring /
   instructions to mention `docs://analysis/{name}` alongside
   `docs://tools/{tool_name}`.

6. **Skill updates:**
   - **layer-rules:** Add rule that changes to `analysis/` functions
     require reviewing `references/analysis/` docs.
   - **code-review:** Extend tool-guide checks to also verify
     analysis docs are current when `analysis/expression.py` changes.

### No formal schema or doc-testing

- Parameters documented in markdown tables (same as tool guides).
- Output shape documented in "Response format" section (columns,
  keys, value types) — no Pydantic schema.
- No dedicated tests for doc examples. Existing unit/integration
  tests cover the functions.

---

## Part 2: `gene_response_profile` — `groups_tested_not_responded`

### Problem

`groups_not_known` conflates "not measured" with "measured but not
significant." For experiments with `significant_only` or
`significant_any_timepoint` table scope on full-genome platforms,
absence of an expression edge means the gene was measured and did
not respond.

### Design decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Coverage heuristic | Scope-only (no gene-count check) | All current `significant_only`/`significant_any_timepoint` experiments are microarray or RNA-seq with full-genome coverage |
| `filtered_subset` treatment | Stays in `groups_not_known` | Too ambiguous — could be "top 34 genes" or "all detected" |
| `table_scopes` in response_summary | Omit | Keep response shape minimal; document in tool guide notes |
| Classification threshold | All experiments in group must have full-coverage scope | Conservative — one `filtered_subset` or `top_n` experiment keeps the group in `groups_not_known` |

### Full-coverage scopes

```python
_FULL_COVERAGE_SCOPES = {"significant_only", "significant_any_timepoint"}
```

A treatment group qualifies for `groups_tested_not_responded` when
every experiment in that group has a `table_scope` value in
`_FULL_COVERAGE_SCOPES`. (Groups in `group_totals` always have ≥1
experiment, so the empty-set edge case doesn't arise.)

### Changes by layer

#### Query layer (`queries_lib.py`)

**`build_gene_response_profile_envelope`:** Add
`collect(DISTINCT e.table_scope) AS table_scopes` to the per-group
aggregation. Return shape changes:

Before: `{group_key, experiments, timepoints}`
After:  `{group_key, experiments, timepoints, table_scopes}`

No changes to `build_gene_response_profile` (main aggregation query).

#### API layer (`functions.py`)

Replace the two-way triage with a three-way split:

```python
_FULL_COVERAGE_SCOPES = {"significant_only", "significant_any_timepoint"}

for gene in genes_dict.values():
    rs = gene["response_summary"]
    gene["groups_responded"] = [
        gk for gk, v in rs.items()
        if v["experiments_up"] > 0 or v["experiments_down"] > 0
    ]
    gene["groups_not_responded"] = [
        gk for gk, v in rs.items()
        if v["experiments_up"] == 0 and v["experiments_down"] == 0
    ]
    missing_groups = [gk for gk in group_totals if gk not in rs]
    gene["groups_tested_not_responded"] = [
        gk for gk in missing_groups
        if set(group_totals[gk]["table_scopes"]) <= _FULL_COVERAGE_SCOPES
    ]
    gene["groups_not_known"] = [
        gk for gk in missing_groups
        if gk not in gene["groups_tested_not_responded"]
    ]
```

#### MCP tool layer (`tools.py`)

Add `groups_tested_not_responded: list[str]` to
`GeneResponseProfileResult` Pydantic model.

#### Analysis layer (`analysis/expression.py`)

In `response_matrix`: treat `groups_tested_not_responded` the same
as `groups_not_responded` → cell value `"not_responded"`.

### Caveat (for tool guide and docs)

> `groups_tested_not_responded` is an inference: experiments with
> `significant_only` or `significant_any_timepoint` scope on
> full-genome platforms imply that absent genes were measured but not
> significant. This holds for microarray and standard RNA-seq. If the
> KG later includes targeted panels with these scopes, this field may
> need revision.

### Cypher verification gate

Before implementing, verify the enriched envelope query against the
live KG:

1. Run the modified envelope Cypher via `run_cypher` to confirm
   `collect(DISTINCT e.table_scope)` returns expected values per
   treatment group.
2. Spot-check with N-stress marker genes (ureA/PMM0965, cynA,
   glnB, glsF, PMM1462) to confirm:
   - Non-nitrogen MED4 treatment groups return
     `significant_only` / `significant_any_timepoint` scopes
   - The triage logic would correctly classify them as
     `groups_tested_not_responded`
3. Only proceed to code changes after verification passes.

### Doc updates

- **`references/tools/gene_response_profile.md`:** Add new field,
  refine "groups_not_known doesn't mean not affected" common mistake,
  add caveat note about the inference.
- **`references/analysis/response_matrix.md`:** Document that
  `groups_tested_not_responded` maps to `"not_responded"`.

### Testing

- **Unit tests:** Mock group_totals with mixed table_scope values,
  verify three-way triage logic.
- **Integration tests (requires KG):** N-stress marker genes:
  - ureA (PMM0965): should have `groups_tested_not_responded` for
    carbon, iron, light, phosphorus, viral, salt — not
    `groups_not_known`.
  - cynA: should remain in `groups_responded` for nitrogen,
    coculture, carbon, iron.
  - Genes with `all_detected_genes` experiments that have
    `not_significant` edges: should remain in
    `groups_not_responded` (unchanged).

---

## Part 3: DataFrame conversion utilities

### Goal

Eliminate boilerplate and silent bugs when converting API results to
DataFrames. The LLM (primary consumer ~90%) forgets to flatten nested
fields, joins lists wrong, or produces CSVs with object-in-cell issues.
A single generic function should make any API result CSV-safe with no
tool-specific knowledge. Dedicated unpackers handle the 2 tools with
secondary tables.

### API surface

Three functions in `multiomics_explorer/analysis/frames.py`, exported
via `multiomics_explorer.analysis.__init__`:

#### `to_dataframe(result)` — universal, works for any tool

```python
from multiomics_explorer.analysis import to_dataframe

df = to_dataframe(result)
```

**Algorithm (no hardcoded column names):**

1. `pd.DataFrame(result["results"])`
2. Walk every column with `dtype == object`:
   - All non-null values are `list` → join with `" | "`
   - All non-null values are `dict` → inline as prefixed columns
     (key `genes_by_status: {"significant_up": 5}` becomes
     `genes_by_status_significant_up: 5`), drop original column
   - Mixed types or deeper nesting → drop column,
     `warnings.warn()` naming the column and suggesting the
     dedicated function if one exists
3. Return a single CSV-safe DataFrame

**Warning behavior:**

Uses `warnings.warn(msg, UserWarning)` — shows up in script stderr,
which the LLM reads after every `uv run`. Hard to miss.

Known suggestions (small lookup dict, not column detection):

| Dropped column | Suggested function |
|----------------|-------------------|
| `response_summary` | `profile_summary_to_dataframe()` |
| `timepoints` | `experiments_to_dataframe()` |

Unknown nested columns get a generic warning:
```
Dropped nested column '{name}' — flatten manually or file an issue.
```

**Dict inlining detail:**

For a column `genes_by_status` with values like
`{"significant_up": 5, "significant_down": 3, "not_significant": 100}`:

- New columns: `genes_by_status_significant_up`,
  `genes_by_status_significant_down`,
  `genes_by_status_not_significant`
- Original `genes_by_status` column dropped
- If dict values are themselves dicts/lists (deeper nesting),
  fall through to the drop-and-warn path

**List joining detail:**

Delimiter: `" | "` (with spaces for readability). Safe because the
KG build pipeline replaces literal `|` with commas before loading.

**Edge cases:**

- `result` has no `"results"` key → raise `ValueError`
- `result["results"]` is empty list → return empty DataFrame
- Column has mix of lists and scalars → treat as mixed, drop with warning
- Column has mix of dicts with different key sets → union of all keys,
  missing keys become NaN

#### `profile_summary_to_dataframe(result)` — gene × group detail

```python
from multiomics_explorer.analysis import profile_summary_to_dataframe

summary_df = profile_summary_to_dataframe(result)
```

Extracts `response_summary` from each gene in `result["results"]`.
One row per gene × group.

**Columns:** `locus_tag`, `gene_name`, `group`,
`experiments_total`, `experiments_tested`, `experiments_up`,
`experiments_down`, `timepoints_total`, `timepoints_tested`,
`timepoints_up`, `timepoints_down`, `up_best_rank`,
`up_median_rank`, `up_max_log2fc`, `down_best_rank`,
`down_median_rank`, `down_max_log2fc`.

Directional fields (`up_best_rank`, etc.) are NaN when no
experiments in that direction.

**Validation:** Raises `ValueError` if `result["results"]` is
missing or if the first result has no `response_summary` key
(wrong tool's result passed in).

#### `experiments_to_dataframe(result)` — experiment × timepoint

```python
from multiomics_explorer.analysis import experiments_to_dataframe

tp_df = experiments_to_dataframe(result)
```

Extracts `timepoints` from each experiment in `result["results"]`.
One row per experiment × timepoint.

**Columns:** All scalar experiment fields, plus per-timepoint:
`timepoint`, `timepoint_order`, `timepoint_hours`,
`tp_gene_count`, `tp_significant_up`, `tp_significant_down`,
`tp_not_significant`.

Non-time-course experiments (no `timepoints` key) get a single
row with timepoint columns as NaN.

`genes_by_status` at experiment level is inlined as
`genes_by_status_significant_up`, etc. (same logic as
`to_dataframe`).

**Validation:** Raises `ValueError` if `result["results"]` is
missing.

### What does NOT get a dedicated function

- **`gene_details`** — sparse but scalar fields. `to_dataframe()`
  handles it (produces NaN columns for missing properties).
- **`kg_schema`** — not tabular (no `results` key). `to_dataframe()`
  raises `ValueError`.
- **`run_cypher`** — unpredictable structure. `to_dataframe()` does
  its best; warns on nested columns.
- **Envelope fields** — direct dict access (`result["by_organism"]`),
  no wrapper needed.

### Reference docs

Add `references/analysis/to_dataframe.md` following the same format
as other analysis reference docs (Part 1). Cover all three functions
in one file since they form a cohesive set.

Register as MCP resource at `docs://analysis/to_dataframe`.

### Impact on research repo

The python-api-guide's "Handling Nested Fields" section (currently
~60 lines of boilerplate) simplifies to:

```python
# Any tool → flat DataFrame
df = to_dataframe(result)

# gene_response_profile → also get the detail table
summary_df = profile_summary_to_dataframe(result)

# list_experiments → also get timepoint detail
tp_df = experiments_to_dataframe(result)
```

### Testing

- **Unit tests (no KG):** Test each code path with synthetic result
  dicts:
  - Flat results (scalars only) → pass-through
  - List columns → joined with `" | "`
  - Dict columns → inlined as prefixed columns
  - Nested dict/list columns → dropped with warning
  - Empty results → empty DataFrame
  - Missing `results` key → ValueError
  - `profile_summary_to_dataframe` on gene_response_profile result
  - `experiments_to_dataframe` on list_experiments result (with and
    without timepoints)
  - Warning message includes function suggestion for known columns
- **Integration tests (requires KG):** Round-trip: call API function,
  pass to `to_dataframe()`, verify `.to_csv()` succeeds and all
  columns are scalar-valued.

---

## Implementation order

1. **Part 1:** Utility reference docs + MCP resource + skill updates
   *(independent)*
2. **Cypher verification gate** *(blocks Part 2)*
3. **Part 2a:** Envelope query enrichment + API triage logic
4. **Part 2b:** MCP tool model update
5. **Part 2c:** `response_matrix` update
6. **Part 2d:** Tool guide and analysis doc updates
7. **Part 2e:** Tests (unit + integration)
8. **Part 3a:** `to_dataframe()` + dedicated unpackers in
   `analysis/frames.py` *(independent of Parts 1-2)*
9. **Part 3b:** Reference doc `references/analysis/to_dataframe.md`
   + MCP resource
10. **Part 3c:** Unit tests
11. **Part 3d:** Integration tests
12. **Part 3e:** Update research repo python-api-guide
