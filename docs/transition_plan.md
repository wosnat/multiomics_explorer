# Transition plan

How to get from the current repo state to the target architecture.
See `architecture_target.md` for the target and
`methodology/llm_omics_analysis.md` for the design rationale.

---

## Current state

```
queries_lib.py  →  build_*() → tuple[str, dict]
     ↓
tools.py  →  calls build_*(), runs execute_query(), formats JSON
     ↓
MCP server  →  returns formatted text
```

- `queries_lib.py` builds Cypher queries (tuple[str, dict])
- `tools.py` does everything else: calls builders, executes queries,
  formats output, applies limits, business logic (dedup, multi-query)
- No public API layer — `__init__.py` is empty
- No tier-1/tier-2 pattern — tools return raw JSON with a limit
- No error handling conventions — mix of return strings and exceptions
- No structured logging or usage tracking
- No docstring acceptance tests
- Several inactive skeleton modules (`agents/`, `ui/`, `evaluation/`)
- Parameter naming inconsistencies (`name` vs `organism_name`, `cnt`
  vs `count`, `limit` in query builders)

## Target state

```
queries_lib.py  →  build_*() → tuple[str, dict]
     ↓
api/functions.py  →  build + execute → list[dict] or dict
     ↓                     ↓
tools.py               scripts (user code)
  tier-1/tier-2          list[dict] → file
  formatted text
  usage logging
```

- `api/` layer between `kg/` and `mcp_server/`
- Public API via `__init__.py` re-exports
- MCP tools call api/, add tier-1/tier-2 formatting
- Consistent parameter names and return field names
- Error handling: api/ raises ValueError, MCP catches all
- Structured logging per layer, usage JSONL log
- Docstring acceptance tests and structure linting
- Regression tests with data diversity (5 per dimension)
- Inactive skeletons removed

---

## Transition steps

Ordered to minimize breakage. Each step is independently committable
and testable. Steps are grouped into phases that correspond to
logical milestones.

### Phase A: Structural refactor (current schema)

These steps work against the current KG schema. No KG rebuild needed.

#### Step 1: Remove inactive modules ✅

Low-risk cleanup. Do first to reduce noise for subsequent steps.

**Modules to remove:**

| Module | Contents | Why remove |
|---|---|---|
| `agents/` | `cypher_agent.py`, `reasoning_agent.py`, `tools.py` | LangChain agent skeleton. Superseded by MCP approach. |
| `ui/` | `app.py` | Streamlit skeleton. Not part of the system. |
| `evaluation/` | `metrics.py` | RAGAS skeleton. Not active. |
| `api/` | `client.py` | Old API client skeleton. Will be replaced by new api/ layer. |
| `config/prompts.yaml` | LangChain prompt templates | Was for the LangChain agent. |

**Dependencies to remove from `pyproject.toml`:**

Check each dependency — remove only if no active code uses it:

| Dependency | Used by | Remove? |
|---|---|---|
| `langchain` | `agents/` | Yes |
| `langgraph` | `agents/` | Yes |
| `langchain-neo4j` | `agents/` | Yes |
| `langchain-openai` | `agents/` | Yes |
| `langchain-anthropic` | `agents/` | Yes |
| `ragas` | `evaluation/` | Yes |
| `streamlit` | `ui/` | Yes |
| `plotly` | `ui/` | Yes |
| `pandas` | `ui/`, analysis scripts | **Keep** — used by extraction/analysis scripts in the agentic workflow |

**Also remove:**
- `tests/evals/test_eval.py` references to removed tools (if any)
- Any imports of removed modules in `__init__.py` files

**Test:** All existing tests still pass. No functional changes.

#### Step 2: Fix parameter and return naming inconsistencies ✅

Fix naming inconsistencies before creating api/, so the api layer
starts clean. These are the conventions defined in
architecture_target.md "Parameter and return conventions".

**Return field renames (Cypher RETURN aliases):**

| Function | Current return field | Target | Impact |
|---|---|---|---|
| `build_list_organisms` | `name` | `organism_name` | Cypher, tools.py formatting, unit tests, regression fixtures |
| `build_list_condition_types` | `cnt` | `count` | Cypher, unit tests, regression fixtures |

**Parameter changes (query builder signatures):**

| Function | Change | Rationale |
|---|---|---|
| `build_search_genes` | Remove `limit` param | Limits are an MCP concern, not a query builder concern |
| `build_gene_overview` | Remove `limit` param | Same |
| `build_query_expression` | Remove `limit` param | Same |
| `build_compare_conditions` | Remove `limit` param (tool being removed anyway) | Same |
| `build_search_ontology` | Remove `limit` param | Same |
| `build_genes_by_ontology` | Remove `limit` param | Same |
| `build_gene_ontology_terms` | Remove `limit` param | Same |

When removing `limit` from builders, remove the `LIMIT $limit` clause
from the generated Cypher. The api/ layer will return all results; the
MCP wrapper applies limits.

**Parameter name standardization:**

| Function | Current param | Target | Notes |
|---|---|---|---|
| `build_gene_overview` | `locus_tags` | `gene_ids` | Match MCP tool param name |
| `build_get_gene_details` | `gene_id` (mapped to `$lt` in Cypher) | `gene_id` (keep, but standardize Cypher param to `$gene_id`) | Internal consistency |

**Decisions to keep (not inconsistencies):**

| Pattern | Why it's correct |
|---|---|
| `gene_id` (singular) in query_expression | It accepts a single gene — singular is right |
| `gene` as return field in expression results | Short form in tabular context, alongside product/organism/log2fc |
| `locus_tag` as return field in search/resolve | Gene is the primary subject, full field name is clearer |
| `identifier` in resolve_gene only | This tool uniquely accepts ambiguous inputs |

**Test updates required:**
- `test_query_builders.py`: Cypher string assertions change (no LIMIT,
  renamed return aliases)
- `test_tool_wrappers.py`: update mocked return data keys
  (`name` → `organism_name`, `cnt` → `count`)
- `test_tool_correctness.py`: update expected keys
- `test_tool_correctness_kg.py`: update expected keys
- Regression fixtures: regenerate (`--force-regen`) — field names
  change in golden files
- Regression `_normalize()`: update sort key detection
  (`name` → `organism_name`, `cnt` removed)

#### Step 3: Create api/ layer

Create `multiomics_explorer/api/` with functions that wrap
query builders + `connection.execute_query`.

For each existing MCP tool, extract query execution + business logic
into an api/ function:

| MCP tool | api/ function | Return type | Business logic moved |
|---|---|---|---|
| `resolve_gene` | `resolve_gene()` | `list[dict]` | — |
| `search_genes` | `search_genes()` | `list[dict]` | Dedup logic |
| `gene_overview` | `gene_overview()` | `dict` | — |
| `get_gene_details` | `get_gene_details()` | `dict` | — |
| `query_expression` | `query_expression()` | `list[dict]` | Will be redefined with new schema |
| `compare_conditions` | — | — | Being removed with KG redesign |
| `get_homologs` | `get_homologs()` | `dict` | Multi-query orchestration (gene stub + groups + members) |
| `list_filter_values` | `list_filter_values()` | `dict` | Combines two queries (categories + conditions) |
| `list_organisms` | `list_organisms()` | `list[dict]` | — |
| `search_ontology` | `search_ontology()` | `list[dict]` | — |
| `genes_by_ontology` | `genes_by_ontology()` | `list[dict]` | — |
| `gene_ontology_terms` | `gene_ontology_terms()` | `list[dict]` | — |
| `run_cypher` | `run_cypher()` | `list[dict]` | Write-keyword blocking |

**Pattern:**

```python
# api/functions.py
def get_homologs(
    gene_id: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    exclude_paralogs: bool = True,
    include_members: bool = False,
    member_limit: int = 50,
    conn: GraphConnection | None = None,
) -> dict:
    """Find orthologs grouped by ortholog group.

    Returns dict with keys:
      query_gene: dict — input gene metadata
      ortholog_groups: list[dict] — groups with counts, function, genera

    Raises ValueError if gene not found or params invalid.
    """
    if conn is None:
        conn = GraphConnection()
    # validation
    if source is not None and source not in VALID_OG_SOURCES:
        raise ValueError(f"Invalid source '{source}'. Valid: {sorted(VALID_OG_SOURCES)}")
    ...
    # multi-query orchestration
    cypher, params = build_gene_stub(gene_id=gene_id)
    gene_rows = conn.execute_query(cypher, **params)
    if not gene_rows:
        raise ValueError(f"Gene '{gene_id}' not found.")
    ...
    return {"query_gene": gene_rows[0], "ortholog_groups": groups}
```

**Key rules:**
- No `limit` parameter — api/ returns everything
- `conn` parameter optional, always last
- Validation raises `ValueError` with specific messages
- Multi-query logic (get_homologs, list_filter_values) lives here
- Docstrings document return dict keys (the contract)

**Tests:**
- `tests/unit/test_api_functions.py` — mock execute_query, verify
  parameter passing, business logic, validation
- `tests/integration/test_api_contract.py` — return key assertions
  against live KG (see architecture doc "Docstring acceptance tests")

#### Step 4: Wire __init__.py

```python
# multiomics_explorer/__init__.py
from multiomics_explorer.api.functions import (
    resolve_gene,
    search_genes,
    gene_overview,
    get_gene_details,
    query_expression,
    get_homologs,
    list_filter_values,
    list_organisms,
    search_ontology,
    genes_by_ontology,
    gene_ontology_terms,
    run_cypher,
)
```

**Test:** `from multiomics_explorer import query_expression` works.

#### Step 5: Rewire MCP tools to call api/

Change each MCP tool from calling queries_lib + execute_query
directly to calling the api/ function.

**Before:**
```python
@mcp.tool()
def get_homologs(ctx, gene_id, source=None, ...):
    conn = _conn(ctx)
    cypher, params = build_gene_stub(gene_id=gene_id)
    gene_rows = conn.execute_query(cypher, **params)
    if not gene_rows:
        return f"Gene '{gene_id}' not found."
    # ... 50 lines of multi-query logic and formatting
```

**After:**
```python
@mcp.tool()
def get_homologs(ctx, gene_id, source=None, ...):
    try:
        conn = _conn(ctx)
        results = api.get_homologs(
            gene_id=gene_id, source=source, ..., conn=conn)
        return _fmt_structured(results)
    except ValueError as e:
        return f"Error: {e}"
```

**This is a pure refactor** — same inputs, same outputs, different
internal call path. All existing tests should pass unchanged.

**Tests:** Update unit tests for tool wrappers to mock api/ instead
of queries_lib. Integration tests should pass unchanged.

#### Step 6: Add error handling pattern

Formalize error handling across layers (see architecture doc
"Error handling"):

- api/ raises `ValueError` for bad inputs (already done in step 3)
- MCP wrappers catch `ValueError` → friendly error text
- MCP wrappers catch `Exception` → generic error text
- MCP tools never raise — always return a string
- Empty results are not errors anywhere

**Test:** Unit tests for each MCP tool: mock api/ to raise ValueError,
assert the tool returns an error string (not raises).

#### Step 7: Add logging

Per architecture doc "Logging":

- `connection.py`: already has `logger.debug` for Cypher — keep
- `api/functions.py`: add `logger.debug` for validation failures
  and multi-query steps
- `mcp_server/tools.py`: add `logger.info` for tool calls + params,
  `logger.warning` for caught errors

Each module uses `logging.getLogger(__name__)`.

**Test:** No dedicated tests — logging is observational. Verify
logs appear during integration test runs.

### Phase B: New behavior

These steps add the new patterns on top of the refactored structure.

#### Step 8: Add tier-1/tier-2 response pattern

For tools with potentially large result sets, add two-tier response.

**Which tools get what:**

| Tool | Pattern | Default limit |
|---|---|---|
| `query_expression` | Full tier-1 summary + tier-2 detail | 100 |
| `search_genes` | Full tier-1 summary + tier-2 detail | 10 |
| `genes_by_ontology` | Full tier-1 summary + tier-2 detail | 25 |
| `get_homologs` | Truncation metadata only | No top-level limit |
| `gene_ontology_terms` | Truncation metadata only | 50 |
| All others | No tiers (small result sets) | — |

**Tier-1 summary fields per tool:**

| Tool | Summary includes |
|---|---|
| `query_expression` | total, direction breakdown, top categories, time points |
| `search_genes` | total, organism breakdown, category breakdown |
| `genes_by_ontology` | total, organism breakdown, genes per term |

**This changes the output format** — existing tests that assert on
output structure will need updating. Do the test updates in this step.

**Tests:**
- Update `test_tool_wrappers.py` for new output format
- Add tier-1 completeness assertions (summary.total matches full
  result count)
- Add truncation metadata assertions
- Update integration tests for new response structure
- Regenerate regression fixtures if tool output format changed

#### Step 9: Add MCP server instructions

Add `instructions` parameter to FastMCP (see methodology doc for
draft content):
- Response format (summary + detail + truncation)
- Don't count truncated rows
- Package import cross-reference for full data

#### Step 10: Update tool docstrings

Rewrite all MCP tool docstrings per architecture doc "Docstring
conventions":
- LLM-facing audience
- Response format description
- Truncation warning for tier-1/tier-2 tools
- Package import cross-reference
- Args with valid values and cross-references to discovery tools

Write api/ function docstrings with return dict key documentation.

#### Step 11: Add docstring acceptance tests

Per architecture doc "Docstring acceptance tests":

- `tests/integration/test_api_contract.py` — return key assertions
  (EXPECTED_KEYS dict, parametrized test per function)
- `tests/unit/test_docstring_structure.py` — MCP docstring lint
  (Args section, truncation warning, package cross-ref for tier tools)

#### Step 12: Add usage logging

Per methodology doc "Usage logging and evaluation":

- Add JSONL logging decorator/helper to `mcp_server/tools.py`
- Each tool call logs: ts, tool, params, result_total,
  result_returned, truncated, duration_ms, error
- Log path: `~/.multiomics_explorer/usage.jsonl` (configurable,
  disableable via env var)

**Test:** Unit test that the log helper writes valid JSONL.

#### Step 13: Expand regression test data diversity

Per architecture doc "Data diversity in regression cases":

Ensure cases.yaml has at least 5 inputs per diversity dimension
for each tool:

| Dimension | Minimum 5 from |
|---|---|
| Organisms | 5 strains spanning Pro HL, Pro LL, Alt, Syn |
| Annotation level | 5 genes across well-annotated, partial, hypothetical |
| Expression availability | 5 genes across rich, sparse, none, coculture, time-course |
| Result size | 5 queries across many, few, empty |

Review existing cases against the diversity matrix, add missing
coverage. Regenerate regression fixtures.

### Phase C: Documentation and cleanup

#### Step 14: Update CLAUDE.md

Update the repo's CLAUDE.md to describe:
- Dual interface (MCP for reasoning, package import for data)
- Layer structure (kg/ → api/ → mcp_server/)
- `analyses/` directory conventions (for in-repo work)
- Tool table updated for new/removed tools

#### Step 15: Merge architecture docs

Replace `architecture.md` with the target architecture. Either:
- Rename `architecture_target.md` → `architecture.md`
- Or merge content, keeping relevant current-state context

Remove `architecture_target.md` and `transition_plan.md` (they've
served their purpose).

---

## What happens in parallel: KG redesign

Steps 1–7 (Phase A) can be done against the **current** KG schema.
The api/ layer wraps existing query builders.

The KG redesign (Experiment nodes, new expression edges) happens in
the KG repo. When the new KG is ready:

- `queries_lib.py` gets new/updated builders for the new schema
- `api/functions.py` gets new/updated functions
  (`list_experiments`, `list_publications`, redefined
  `query_expression`)
- `mcp_server/tools.py` gets new/updated tool wrappers
- `compare_conditions` tool is removed
- Step 8 (tier-1/tier-2) is implemented on the new tools

The layer structure from Phase A makes this clean — new schema
means new query builders → new api/ functions → new tool wrappers.
Each layer changes independently.

---

## Step dependencies

```
Phase A: Structural refactor
  Step 1  (remove skeletons) ─────────────────────────────┐
  Step 2  (fix naming) ──→ Step 3 (api/ layer) ──→ Step 4 │
                                    │              (__init__)
                                    ▼                │
                           Step 5 (rewire MCP) ◀─────┘
                                    │
                                    ▼
                           Step 6 (error handling)
                           Step 7 (logging)

Phase B: New behavior (after Phase A)
  Step 8  (tier-1/tier-2) ──→ Step 9  (MCP instructions)
                               Step 10 (docstrings)
                               Step 11 (docstring tests)
  Step 12 (usage logging) — independent within Phase B
  Step 13 (regression diversity) — independent within Phase B

Phase C: Documentation (after Phase B)
  Step 14 (CLAUDE.md)
  Step 15 (merge architecture docs)
```

Phase A steps are sequential (each depends on the previous).
Phase B steps can be partially parallelized.
Phase C waits until everything else is done.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Step 5 (rewire MCP) breaks output format | Integration tests fail | Pure refactor — same output, different call path. Verify all tests pass before step 8. |
| Step 8 (tier-1/tier-2) changes output format | Integration tests fail, regression fixtures stale | Update tests and regenerate fixtures in the same commit. |
| Step 2 (naming fixes) breaks downstream | Integration tests, regression fixtures, possibly external scripts | Do before api/ layer exists, so only internal code is affected. |
| KG redesign lands mid-transition | Merge conflicts, unclear what's new vs refactored | Complete Phase A first. KG redesign is a Phase B concern. |
| Regression fixture regeneration loses old baselines | Can't compare before/after | Git history preserves old fixtures. Regenerate on a dedicated commit with clear message. |
