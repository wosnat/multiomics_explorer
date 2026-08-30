# LLM-review 2b.5 — schema diet — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut `tools/list` from 523 KB to ~170 KB and the 42 tool descriptions from ~9.9k to ≤6.3k tokens, and align every parameter name to the house style (R1–R4) — with zero change to any response shape.

**Architecture:** Four independent edits to the MCP layer plus one to the Python API: (1) `output_schema=None` on every tool with the docs generator reading the Pydantic return models directly; (2) a `_deprecated_alias` helper in `api/` so old keywords keep working for one release while MCP wrappers expose canonical names only; (3) shared `Annotated` param types in a new `mcp_server/params.py`; (4) every docstring rewritten to the five-slot template under a 600-char lint. Rules land in `.claude/skills/layer-rules`, not in outfacing docs, and a contract test over `tools/list` keeps them true.

**Tech Stack:** Python 3.12, FastMCP 3.1 / Pydantic v2, pytest (`tests/unit/` needs no Neo4j; `-m kg` needs the live KG at `localhost:7687`), `scripts/build_about_content.py` (generated tool docs + `--lint`), `scripts/refresh_examples.py`.

**Spec:** `docs/superpowers/specs/2026-08-30-llm-review-2b5-schema-diet-design.md` — decisions D1–D6, rules R1–R4, the template, the shared-type list.

## Global Constraints

- Branch `llm-review-2b5` off `main`; never merge, never push. Worktree via `superpowers:using-git-worktrees`, then `git reset --hard main` before the first task.
- No tool added or removed. No envelope key or row field added, removed, renamed or retyped — regression `--force-regen` at the end must show a zero diff.
- MCP input schemas expose canonical parameter names only. Deprecated aliases exist in `api/functions.py` only, removed in alpha.6.
- `has_p_value`, `significant_only`, `max_adjusted_p_value` and the p-value row fields are untouched (spec D5).
- Outfacing text (docstrings, `Field(description=...)`, YAML, generated md): no dates, no changelog words ("now", "previously", "renamed", "was") — the existing lints enforce it. Every tool docstring ≤ 600 characters after Task 8.
- Rules text goes to `.claude/skills/layer-rules/`, never to `docs://guide/conventions`.
- Read `.claude/skills/layer-rules/SKILL.md` and `.claude/skills/testing/SKILL.md` before Task 1.
- Every task ends with `uv run pytest tests/unit -q -p no:cacheprovider` green, then `uv run python scripts/build_about_content.py && uv run python scripts/build_about_content.py --lint` clean (regenerated md is committed with the task).
- Commit per task with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Drop `outputSchema` from the wire; generator reads the return models

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py:1547-1560` (`register_tools` head; 42 `@mcp.tool(` decorators below it)
- Modify: `scripts/build_about_content.py:112-138` (`get_tool_schemas`)
- Modify: `tests/unit/test_about_content.py:28-46` (its private schema extractor — same change)
- Modify: `.claude/skills/layer-rules/SKILL.md:38-47` (Layer 3 paragraph)
- Test: `tests/unit/test_tool_wrappers.py`

**Interfaces:**
- Produces: `get_tool_schemas()` still returns `{name: {"description", "parameters", "output_schema"}}` with `output_schema` populated — from `tool.fn.__annotations__["return"].model_json_schema()` instead of `to_mcp_tool().outputSchema`. Downstream generator code (`extract_response_fields`) is untouched.

- [ ] **Step 1: Write the failing test** (append to `tests/unit/test_tool_wrappers.py`):

```python
def test_no_tool_emits_output_schema():
    """Spec D1: outputSchema is never sent on tools/list (the host never passes it to the model)."""
    import asyncio
    from fastmcp import FastMCP
    from multiomics_explorer.mcp_server.tools import register_tools

    mcp = FastMCP("t")
    register_tools(mcp)

    async def _run():
        return [(t.name, t.to_mcp_tool().outputSchema) for t in await mcp.list_tools()]

    leaking = [name for name, schema in asyncio.run(_run()) if schema]
    assert leaking == [], f"tools still emitting outputSchema: {leaking}"
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_tool_wrappers.py::test_no_tool_emits_output_schema -q -p no:cacheprovider` → FAIL listing 42 tools.

- [ ] **Step 3: Implement.** In `register_tools`, immediately after the docstring, shadow the decorator once so no per-tool edit is needed:

```python
def register_tools(mcp: FastMCP):
    """Register all KG tools with the MCP server."""
    # Spec 2b.5 D1: outputSchema is client-side only and never reaches the
    # model; the response shape the model reads is the docstring's
    # "Returns" slot + docs://tools/{name}. structuredContent is unaffected.
    _tool = mcp.tool

    def _tool_no_output_schema(*args, **kwargs):
        kwargs.setdefault("output_schema", None)
        return _tool(*args, **kwargs)

    mcp.tool = _tool_no_output_schema  # type: ignore[method-assign]
```

Then run the test again → PASS. (Every `@mcp.tool(...)` below now passes `output_schema=None`; the return annotations stay so `structuredContent` is still produced — verify with the POC from the spec if in doubt: `Client(mcp).call_tool("kg_release_info")` has `structured_content`.)

- [ ] **Step 4: Fix the generator.** Replace the extractor body in `scripts/build_about_content.py::get_tool_schemas`:

```python
    async def _extract():
        tools = await mcp.list_tools()
        schemas = {}
        for t in tools:
            tool = await mcp.get_tool(t.name)
            mcp_tool = tool.to_mcp_tool()
            ret = tool.fn.__annotations__.get("return")
            output_schema = ret.model_json_schema() if ret is not None and hasattr(ret, "model_json_schema") else None
            schemas[t.name] = {
                "description": mcp_tool.description or "",
                "parameters": mcp_tool.inputSchema,
                "output_schema": output_schema,
            }
        return schemas
```

Apply the identical replacement to the extractor in `tests/unit/test_about_content.py:28-46`. Add to `tests/unit/test_about_content.py`:

```python
def test_get_tool_schemas_has_output_schema_from_return_model():
    schemas = _get_schemas()          # the module's existing helper name — keep whatever it is called
    assert schemas["list_organisms"]["output_schema"]["properties"]["results"]
    assert all(s["output_schema"] for s in schemas.values()), "every tool has a typed return model"
```

- [ ] **Step 5: Verify the docs are byte-identical.** `git stash -- multiomics_explorer/skills` is NOT needed: run `uv run python scripts/build_about_content.py && git status --short multiomics_explorer/skills` → no output (nothing regenerated differently). If a file changed, diff it: the only acceptable difference is `$defs` ordering; fix the extractor to match `to_mcp_tool()`'s output if anything else moved.

- [ ] **Step 6: Layer-rules text.** In `.claude/skills/layer-rules/SKILL.md` Layer 3, replace the line `Pydantic response models → FastMCP auto-generates \`outputSchema\`.` with:

```
Pydantic response models validate the payload; `register_tools` passes
`output_schema=None` for every tool (the model never sees outputSchema —
the docstring's "Returns" slot + docs://tools/{name} carry the shape).
```

- [ ] **Step 7: Run** `uv run pytest tests/unit -q -p no:cacheprovider` → green; `uv run python scripts/build_about_content.py --lint` → clean.

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py scripts/build_about_content.py tests/unit/test_tool_wrappers.py tests/unit/test_about_content.py .claude/skills/layer-rules/SKILL.md
git commit -m "perf(mcp): drop outputSchema from tools/list; generator reads return models (llm-review 2b.5 D1)"
```

---

### Task 2: `_deprecated_alias` helper for the Python API

**Files:**
- Create: `multiomics_explorer/api/_compat.py`
- Test: `tests/unit/test_api_compat.py`

**Interfaces:**
- Produces: `def deprecated_alias(*, old: Any, new: Any, old_name: str, new_name: str, listify: bool = False) -> Any` — returns the resolved value for `new_name`. Rules: `old is None` → return `new`; both non-None → `ValueError`; `old` given → `warnings.warn(DeprecationWarning)` and return `old`; when `listify=True` a `str` (from either side) is wrapped as `[value]`. Tasks 3–6 call it at the top of every renamed API function.

- [ ] **Step 1: Write the failing tests** (`tests/unit/test_api_compat.py`):

```python
import warnings
import pytest
from multiomics_explorer.api._compat import deprecated_alias


def test_new_only_passes_through():
    assert deprecated_alias(old=None, new=[1], old_name="publication_doi", new_name="publication_dois") == [1]


def test_old_warns_and_is_used():
    with pytest.warns(DeprecationWarning, match="publication_doi.*publication_dois"):
        out = deprecated_alias(old=["x"], new=None, old_name="publication_doi", new_name="publication_dois")
    assert out == ["x"]


def test_both_raises():
    with pytest.raises(ValueError, match="both"):
        deprecated_alias(old=1, new=2, old_name="min_value", new_name="min_value")


def test_listify_wraps_bare_str():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert deprecated_alias(old=None, new="coculture", old_name="treatment_type", new_name="treatment_type", listify=True) == ["coculture"]
        assert deprecated_alias(old="nitrogen", new=None, old_name="category", new_name="gene_categories", listify=True) == ["nitrogen"]


def test_none_none_is_none():
    assert deprecated_alias(old=None, new=None, old_name="a", new_name="b") is None
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_api_compat.py -q -p no:cacheprovider` → FAIL (ImportError).

- [ ] **Step 3: Implement** `multiomics_explorer/api/_compat.py`:

```python
"""One-release keyword aliases for renamed Python-API parameters (spec 2b.5 D4).

Every alias here is scheduled for removal in explorer 0.1.0-alpha.6. The MCP
layer never uses these names — MCP schemas expose canonical names only.
"""
from __future__ import annotations

import warnings
from typing import Any


def deprecated_alias(
    *, old: Any, new: Any, old_name: str, new_name: str, listify: bool = False
) -> Any:
    """Resolve a renamed keyword: returns the value to use for ``new_name``.

    ``old`` set → DeprecationWarning and ``old`` is used. Both set → ValueError.
    ``listify=True`` wraps a bare ``str`` as a one-element list (the parameter is
    declared ``list[str]``; a bare string would otherwise iterate per character).
    """
    if old is not None and new is not None:
        raise ValueError(
            f"Pass either {new_name!r} or the deprecated {old_name!r}, not both."
        )
    if old is not None:
        warnings.warn(
            f"{old_name!r} is deprecated and will be removed in 0.1.0-alpha.6; "
            f"use {new_name!r}.",
            DeprecationWarning,
            stacklevel=3,
        )
        value = old
    else:
        value = new
    if listify and isinstance(value, str):
        value = [value]
    return value
```

- [ ] **Step 4: Run** the test file → PASS. Then `uv run pytest tests/unit -q -p no:cacheprovider` → green.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/api/_compat.py tests/unit/test_api_compat.py
git commit -m "feat(api): deprecated_alias helper for one-release keyword aliases (llm-review 2b.5 D4)"
```

---

### Task 3: R1 — range params become `min_x` / `max_x` on the two metabolomics tools

**Files:**
- Modify: `multiomics_explorer/api/functions.py:9595-…` (`metabolites_by_quantifies_assay`), `:7791-…` (`list_metabolites`)
- Modify: `multiomics_explorer/mcp_server/tools.py` — the `metabolites_by_quantifies_assay` and `list_metabolites` wrappers (grep `value_min: Annotated`, `mass_min: Annotated`)
- Modify: `multiomics_explorer/inputs/tools/metabolites_by_quantifies_assay.yaml`, `list_metabolites.yaml` (examples / mistakes / chaining that use the old names), `multiomics_explorer/inputs/tools/assays_by_metabolite.yaml` and any other yaml whose `chaining` cites them (`grep -ln "value_min\|rank_by_metric_max\|metric_percentile_m\|mass_min\|mass_max" multiomics_explorer/inputs/tools/*.yaml`)
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md`, `examples/metabolites.py` (grep the same names under `multiomics_explorer/skills/`)
- Test: `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py`, `tests/integration/test_mcp_tools.py`, `tests/integration/test_api_contract.py`, `tests/evals/cases.yaml` (grep the old names)

**Renames:** `value_min`→`min_value`, `value_max`→`max_value`, `metric_percentile_min`→`min_percentile`, `metric_percentile_max`→`max_percentile`, `rank_by_metric_max`→`max_rank` (assay tool); `mass_min`→`min_mass`, `mass_max`→`max_mass` (`list_metabolites`). Query-builder keyword names in `kg/queries_lib.py` are NOT renamed (Layer 1 is internal); the API function maps canonical → builder kwarg.

**Interfaces:**
- Produces: canonical keyword names on both API functions; old keywords remain as trailing keyword-only parameters defaulting to `None`, resolved via `deprecated_alias`.

- [ ] **Step 1: Failing API tests** (append to `tests/unit/test_api_functions.py`, using the file's existing mocked-connection fixture — look at the nearest `metabolites_by_quantifies_assay` test for the fixture name and copy its setup):

```python
def test_mbqa_min_value_canonical_and_alias(mock_conn_for_mbqa):
    from multiomics_explorer.api import functions as api
    api.metabolites_by_quantifies_assay(assay_ids=["a1"], min_value=0.5, conn=mock_conn_for_mbqa)
    q, params = mock_conn_for_mbqa.last_query  # adapt to the fixture's capture API
    assert params["value_min"] == 0.5          # builder kwarg unchanged
    with pytest.warns(DeprecationWarning):
        api.metabolites_by_quantifies_assay(assay_ids=["a1"], value_min=0.5, conn=mock_conn_for_mbqa)
    with pytest.raises(ValueError):
        api.metabolites_by_quantifies_assay(assay_ids=["a1"], value_min=0.5, min_value=0.5, conn=mock_conn_for_mbqa)


def test_list_metabolites_min_mass_alias(mock_conn_for_list_metabolites):
    from multiomics_explorer.api import functions as api
    with pytest.warns(DeprecationWarning):
        api.list_metabolites(mass_min=100.0, conn=mock_conn_for_list_metabolites)
```

Write one such pair per renamed keyword (7 keywords) — a `@pytest.mark.parametrize("old,new", [...])` over the five assay names is fine.

- [ ] **Step 2: Failing wrapper test** (append to `tests/unit/test_tool_wrappers.py`). First add the module helper every later task reuses:

```python
def _all_tool_input_schemas() -> dict[str, dict]:
    """{tool_name: inputSchema} from a fresh FastMCP with register_tools (no Neo4j)."""
    import asyncio
    from fastmcp import FastMCP
    from multiomics_explorer.mcp_server.tools import register_tools

    mcp = FastMCP("t")
    register_tools(mcp)

    async def _run():
        return {t.name: t.to_mcp_tool().inputSchema for t in await mcp.list_tools()}

    return asyncio.run(_run())
```

then the test:

```python
@pytest.mark.parametrize("tool,expected,forbidden", [
    ("metabolites_by_quantifies_assay",
     {"min_value", "max_value", "min_percentile", "max_percentile", "max_rank"},
     {"value_min", "value_max", "metric_percentile_min", "metric_percentile_max", "rank_by_metric_max"}),
    ("list_metabolites", {"min_mass", "max_mass"}, {"mass_min", "mass_max"}),
])
def test_r1_range_param_names(tool, expected, forbidden):
    props = set(_all_tool_input_schemas()[tool]["properties"])
    assert expected <= props
    assert not (forbidden & props)
```

- [ ] **Step 3: Run** both files → FAIL.

- [ ] **Step 4: Implement the API side.** In `metabolites_by_quantifies_assay` change the signature parameters to the canonical names and append deprecated ones after `*`:

```python
def metabolites_by_quantifies_assay(
    ...,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    max_rank: int | None = None,
    ...,
    *,
    conn: GraphConnection | None = None,
    value_min: float | None = None,
    value_max: float | None = None,
    metric_percentile_min: float | None = None,
    metric_percentile_max: float | None = None,
    rank_by_metric_max: int | None = None,
) -> dict:
    min_value = deprecated_alias(old=value_min, new=min_value, old_name="value_min", new_name="min_value")
    max_value = deprecated_alias(old=value_max, new=max_value, old_name="value_max", new_name="max_value")
    min_percentile = deprecated_alias(old=metric_percentile_min, new=min_percentile, old_name="metric_percentile_min", new_name="min_percentile")
    max_percentile = deprecated_alias(old=metric_percentile_max, new=max_percentile, old_name="metric_percentile_max", new_name="max_percentile")
    max_rank = deprecated_alias(old=rank_by_metric_max, new=max_rank, old_name="rank_by_metric_max", new_name="max_rank")
```

Then pass `value_min=min_value, …` into the builder call(s) exactly where the old local names were used (grep the function body for each old name and substitute). `from multiomics_explorer.api._compat import deprecated_alias` at the module top. Same pattern for `list_metabolites` (`min_mass` / `max_mass`).

- [ ] **Step 5: Implement the MCP side.** In the two wrappers rename the `Annotated` parameters (`value_min: Annotated[...]` → `min_value: Annotated[...]`, etc.), update the `api.…(` call to pass canonical names, and rewrite any description text that names the old keyword (e.g. "pair with `value_min`") to the new one. Descriptions get their full rewrite in Task 8 — only fix references here.

- [ ] **Step 6: Sweep every other mention.** `grep -rn "value_min\|value_max\|metric_percentile_min\|metric_percentile_max\|rank_by_metric_max\|mass_min\|mass_max" --include=*.py --include=*.yaml --include=*.md multiomics_explorer tests docs/superpowers/specs/2026-08-30-llm-review-2b5-schema-diet-design.md /home/osnat/github/multiomics_research` and fix each hit that is a *parameter name* (leave row-field names such as `metric_percentile` and query-builder kwargs alone; leave the spec and CHANGELOG history alone). `tests/evals/cases.yaml` and the research repo count as callers.

- [ ] **Step 7: Run** `uv run pytest tests/unit -q -p no:cacheprovider` → green; `uv run pytest -m kg tests/integration -q -p no:cacheprovider -k "quantifies_assay or list_metabolites"` → green; `uv run python scripts/build_about_content.py && uv run python scripts/build_about_content.py --lint` → clean; `uv run python scripts/refresh_examples.py --check metabolites_by_quantifies_assay list_metabolites` → ok (no `error`).

- [ ] **Step 8: Commit**

```bash
git add -A multiomics_explorer tests scripts
git commit -m "refactor(api,mcp): R1 range params are min_x/max_x on the metabolomics tools (llm-review 2b.5)"
```

(Commit research-repo edits separately in that repo: `refactor: follow explorer 2b.5 param renames`.)

---

### Task 4: R3 — `publication_doi` → `publication_dois` on 11 tools

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — the 12 functions with `publication_doi: list[str] | None` (`grep -n "    publication_doi: " multiomics_explorer/api/functions.py`)
- Modify: `multiomics_explorer/mcp_server/tools.py` — the 11 wrappers (`grep -n "publication_doi: Annotated" multiomics_explorer/mcp_server/tools.py`) plus every `Field(description=...)` / docstring that says `publication_doi=[...]` as a *call* (`grep -n "publication_doi=" multiomics_explorer/mcp_server/tools.py`)
- Modify: `multiomics_explorer/inputs/tools/*.yaml` (5 files use it in examples/chaining), `multiomics_explorer/skills/multiomics-kg-guide/references/{guide,analysis}/*.md`, `examples/*.py`
- Test: `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py`, `tests/integration/*.py`, `tests/evals/cases.yaml`, research repo (10 files)

**Interfaces:**
- Produces: `publication_dois: list[str] | None` on all 13 API functions / 13 tools; `publication_doi` kept as a deprecated keyword-only alias in the API.

- [ ] **Step 1: Failing wrapper test** (append to `tests/unit/test_tool_wrappers.py`):

```python
def test_r3_publication_dois_everywhere():
    """R3: ID batches are plural — no tool exposes the singular list-typed name."""
    schemas = _all_tool_input_schemas()
    singular = [n for n, s in schemas.items() if "publication_doi" in s["properties"]]
    assert singular == [], singular
    plural = [n for n, s in schemas.items() if "publication_dois" in s["properties"]]
    assert len(plural) == 13, plural
```

- [ ] **Step 2: Failing API test** (parametrized over the 11 functions; use each function's existing mocked fixture — if one is awkward, mock `GraphConnection.execute_query` to return `[]`):

```python
@pytest.mark.parametrize("fn_name", [
    "list_experiments", "list_clustering_analyses", "gene_clusters_by_gene",
    "list_derived_metrics", "gene_derived_metrics", "genes_by_numeric_metric",
    "genes_by_boolean_metric", "genes_by_categorical_metric",
    "list_metabolite_assays", "metabolites_by_quantifies_assay", "metabolites_by_flags_assay",
])
def test_publication_doi_alias_warns(fn_name, empty_conn):
    from multiomics_explorer.api import functions as api
    fn = getattr(api, fn_name)
    with pytest.warns(DeprecationWarning, match="publication_doi"):
        fn(publication_doi=["10.1/x"], conn=empty_conn, **_REQUIRED_ARGS.get(fn_name, {}))
```

`_REQUIRED_ARGS` supplies mandatory positional inputs (e.g. `{"gene_derived_metrics": {"locus_tags": ["PMM0001"]}, "gene_clusters_by_gene": {"locus_tags": ["PMM0001"]}}`; check each signature). Confirm the exact 11-name list against the grep in Step 4 before committing the parametrize list.

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement.** For each API function: rename the parameter to `publication_dois`, add `publication_doi: list[str] | None = None` after `*`, first statement `publication_dois = deprecated_alias(old=publication_doi, new=publication_dois, old_name="publication_doi", new_name="publication_dois")`, and pass `publication_doi=publication_dois` to the builder (builder kwarg unchanged). For each MCP wrapper: rename the `Annotated` parameter and the `api.…(publication_dois=publication_dois)` call. Then `grep -rn "publication_doi\b" multiomics_explorer tests --include=*.py --include=*.yaml --include=*.md | grep -v "publication_dois\|_compat\|old_name\|publication_doi: list\[str\] | None = None"` and fix every remaining *call-site / parameter* mention (row fields named `publication_doi` on results are NOT parameters — leave them). Repeat the grep in the research repo.

- [ ] **Step 5: Run** unit → green; `uv run pytest -m kg tests/integration -q -p no:cacheprovider -k "publication"` → green; docs regenerated + `--lint` clean; `uv run python scripts/refresh_examples.py --check` for the 5 yaml files touched → no `error`.

- [ ] **Step 6: Commit**

```bash
git add -A multiomics_explorer tests
git commit -m "refactor(api,mcp): R3 publication_doi -> publication_dois on 13 tools (llm-review 2b.5)"
```

---

### Task 5: R4 — filters named after the row field; `direction='both'` on the ortholog tool

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `genes_by_numeric_metric` (`bucket`), `genes_by_boolean_metric` (`flag`), `genes_by_function` (`category`), `differential_expression_by_ortholog` (`_VALID_DIRECTIONS_BY_ORTHOLOG` at `:4258`)
- Modify: `multiomics_explorer/kg/queries_lib.py` — `build_genes_by_function` (`:1003`, `:1047`: `category: str | None` → `gene_categories: list[str] | None`, condition `g.gene_category IN $gene_categories`); `build_differential_expression_by_ortholog*` (`:5762`: add the `both` branch exactly as `:5011` has it)
- Modify: `multiomics_explorer/mcp_server/tools.py` — the three wrappers + the ortholog `direction` Literal (`:5375`)
- Modify: yaml / md / examples citing `bucket=`, `flag=`, `category=` for these tools
- Test: `tests/unit/test_query_builders.py`, `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py`, `tests/integration/test_mcp_tools.py`, `tests/evals/cases.yaml`, research repo (`bucket=` 12 files, `flag=` 3, `category=` — only `genes_by_function` calls, most of the 98 hits are unrelated)

**Interfaces:**
- Produces: `genes_by_numeric_metric(metric_bucket=...)`, `genes_by_boolean_metric(flag_value=...)`, `genes_by_function(gene_categories: list[str] | None)`, `differential_expression_by_ortholog(direction in {"up","down","both"})`. Aliases `bucket`, `flag`, `category` (listified) in the API.
- `by_category` envelope key on `genes_by_function` is unchanged (it is a rollup, not the filter).

- [ ] **Step 1: Failing query-builder tests** (`tests/unit/test_query_builders.py`):

```python
def test_genes_by_function_gene_categories_list():
    from multiomics_explorer.kg.queries_lib import build_genes_by_function
    q, p = build_genes_by_function(search_text="urea", gene_categories=["transport", "metabolism"])
    assert "g.gene_category IN $gene_categories" in q
    assert p["gene_categories"] == ["transport", "metabolism"]


def test_de_by_ortholog_direction_both():
    from multiomics_explorer.kg.queries_lib import build_differential_expression_by_ortholog
    q, p = build_differential_expression_by_ortholog(group_ids=["g1"], direction="both")
    assert "IN ['significant_up', 'significant_down']" in q
```

(Use the real builder names — `grep -n "^def build_differential_expression_by_ortholog\|^def build_genes_by_function" multiomics_explorer/kg/queries_lib.py` — and add the `both` branch to every ortholog builder that has the `up`/`down` branches.)

- [ ] **Step 2: Failing API + wrapper tests:**

```python
def test_genes_by_numeric_metric_metric_bucket_alias(empty_conn):
    from multiomics_explorer.api import functions as api
    with pytest.warns(DeprecationWarning, match="bucket"):
        api.genes_by_numeric_metric(derived_metric_ids=["dm1"], bucket="high", conn=empty_conn)

def test_genes_by_boolean_metric_flag_alias(empty_conn):
    from multiomics_explorer.api import functions as api
    with pytest.warns(DeprecationWarning, match="flag"):
        api.genes_by_boolean_metric(derived_metric_ids=["dm1"], flag=True, conn=empty_conn)

def test_genes_by_function_category_alias_listifies(mock_conn_for_genes_by_function):
    from multiomics_explorer.api import functions as api
    with pytest.warns(DeprecationWarning, match="category"):
        api.genes_by_function("urea", category="transport", conn=mock_conn_for_genes_by_function)
    assert mock_conn_for_genes_by_function.last_params["gene_categories"] == ["transport"]

def test_de_by_ortholog_accepts_both(empty_conn):
    from multiomics_explorer.api import functions as api
    api.differential_expression_by_ortholog(group_ids=["g1"], direction="both", conn=empty_conn)  # must not raise
```

Wrapper test (parametrized like Task 3's): `genes_by_numeric_metric` has `metric_bucket` not `bucket`; `genes_by_boolean_metric` has `flag_value` not `flag`; `genes_by_function` has `gene_categories` (array) not `category`; `differential_expression_by_ortholog`'s `direction` enum contains `both`.

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement** per Task 3's pattern (API: canonical param + keyword-only alias + `deprecated_alias`; `genes_by_function` uses `listify=True`; MCP: rename `Annotated` params, pass canonical). `flag_value` on `genes_by_boolean_metric` keeps its `bool | None` semantics; `_closed_vocab_warnings(conn, category=category)` at `functions.py:1450` becomes a loop over `gene_categories` (or pass the list if the helper accepts one — read it). Add `"both"` to `_VALID_DIRECTIONS_BY_ORTHOLOG` and to the wrapper's `Literal`. Sweep old names as in Task 3 Step 6.

- [ ] **Step 5: Run** unit → green; `uv run pytest -m kg tests/integration -q -p no:cacheprovider -k "genes_by_function or numeric_metric or boolean_metric or by_ortholog"` → green; docs regenerated + `--lint` clean; `refresh_examples.py --check` for the four yaml files.

- [ ] **Step 6: Commit**

```bash
git add -A multiomics_explorer tests
git commit -m "refactor(api,mcp): R4 filters named after row fields; direction='both' on ortholog DE (llm-review 2b.5)"
```

---

### Task 6: R2 — vocabulary filters are `list[str]` under the KG property name; shared `OntologyKey`

**Files:**
- Create: `multiomics_explorer/mcp_server/params.py` (only `OntologyKey` in this task; Task 7 fills the rest)
- Modify: `multiomics_explorer/kg/queries_lib.py` — `build_list_publications*` (`treatment_type`, `background_factors`, `growth_phases` conditions become `any(x IN $treatment_type WHERE x IN e.treatment_type)` / `any(x IN $background_factors WHERE x IN coalesce(e.background_factors, []))` / `toLower(r.growth_phase) IN $growth_phases` — copy the exact forms `build_list_experiments` uses); `build_list_clustering_analyses*` and `build_list_derived_metrics*` (`omics_type` → `IN $omics_type`, copy `build_list_experiments`)
- Modify: `multiomics_explorer/api/functions.py` — `list_publications` (`:2447`), `list_clustering_analyses` (`:5053`), `list_derived_metrics` (`:5211`), `gene_response_profile` (`:4850`, `treatment_types` → `treatment_type`)
- Modify: `multiomics_explorer/mcp_server/tools.py` — the four wrappers; `search_ontology` `ontology` (`:2843`) and `list_filter_values` `ontology` (`:1777`) typed with `OntologyKey`; the three single-ontology tools and the two multi-ontology tools switched to `OntologyKey` / `list[OntologyKey] | OntologyKey`
- Test: `tests/unit/test_query_builders.py`, `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py`, `tests/unit/test_params.py` (new), integration + evals + research repo (`treatment_types=` 2 test files)

**Interfaces:**
- Produces: `OntologyKey = Literal["go_bp", "go_mf", "go_cc", "ec", "kegg", "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite", "tcdb", "cazy", "subcellular_localization", "signal_peptide_type", "interpro", "ncbifam", "merops"]` in `params.py` (order = `ONTOLOGY_CONFIG`). API: `list_publications(treatment_type: list[str] | None, background_factors: list[str] | None, growth_phases: list[str] | None)` — a bare `str` still works via `deprecated_alias(listify=True)` with the *same* name (old=None path just listifies; no warning); `list_clustering_analyses` / `list_derived_metrics` `omics_type: list[str] | None` likewise; `gene_response_profile(treatment_type=...)` with `treatment_types` alias.

- [ ] **Step 1: Failing tests.** `tests/unit/test_params.py`:

```python
from typing import get_args
from multiomics_explorer.api.functions import ONTOLOGY_CONFIG
from multiomics_explorer.mcp_server.params import OntologyKey

def test_ontology_key_matches_registry():
    assert get_args(OntologyKey) == tuple(ONTOLOGY_CONFIG)
```

Wrapper test (append to `tests/unit/test_tool_wrappers.py`):

```python
_VOCAB = ("treatment_type", "background_factors", "growth_phases", "omics_type", "compartment")

def test_r2_vocab_filters_are_lists_everywhere():
    for name, s in _all_tool_input_schemas().items():
        for p in _VOCAB:
            if p in s["properties"]:
                assert _is_string_array(s["properties"][p]), f"{name}.{p} is not list[str]"
        assert "treatment_types" not in s["properties"], name

def test_ontology_param_is_enum_everywhere():
    keys = set(get_args(OntologyKey))
    for name, s in _all_tool_input_schemas().items():
        if "ontology" in s["properties"]:
            assert _enum_values(s["properties"]["ontology"]) == keys, name
```

Implement `_is_string_array(prop)` (handles `{"type":"array","items":{"type":"string"}}` inside an `anyOf` with null) and `_enum_values(prop)` (collects every `enum` list found under `anyOf` / `items`; returns a set) as module helpers in the test file. Query-builder tests: one per changed builder asserting the new `IN $…` / `any(...)` fragment and that a list param is emitted. API test: `list_publications(treatment_type="coculture", conn=...)` sends `["coculture"]`; `gene_response_profile(treatment_types=[...])` warns.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement** builders (copy `build_list_experiments` fragments verbatim), API (`treatment_type = deprecated_alias(old=None, new=treatment_type, old_name="treatment_type", new_name="treatment_type", listify=True)` for the same-name cases; full alias for `treatment_types`), `params.py` with `OntologyKey`, and the six `ontology` annotations in `tools.py`. `list_filter_values.ontology` becomes `OntologyKey | None`; `search_ontology.ontology` becomes `list[OntologyKey] | OntologyKey | None`.

- [ ] **Step 4: Run** unit → green; `uv run pytest -m kg tests/integration -q -p no:cacheprovider -k "publications or clustering or derived_metrics or response_profile or search_ontology or filter_values"` → green; docs + `--lint`; `refresh_examples.py --check list_publications list_clustering_analyses list_derived_metrics gene_response_profile search_ontology`.

- [ ] **Step 5: Commit**

```bash
git add -A multiomics_explorer tests
git commit -m "refactor(kg,api,mcp): R2 vocab filters are list[str] under the KG property name; shared OntologyKey (llm-review 2b.5)"
```

---

### Task 7: Shared `Annotated` param types

**Files:**
- Modify: `multiomics_explorer/mcp_server/params.py`
- Modify: `multiomics_explorer/mcp_server/tools.py` — every occurrence of the listed params (the `_TRUST_*_DESC` constants at `:1551-1600` move into `params.py` as the trust types)
- Test: `tests/unit/test_params.py`, `tests/unit/test_tool_wrappers.py`

**Interfaces:**
- Produces, in `params.py` (each an `Annotated[<type>, Field(description=...)]`; the default stays on the tool signature):

| Name | Type | Description (final text — ≤ 160 chars each) |
|---|---|---|
| `OrganismParam` | `str \| None` | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| `OrganismsParam` | `list[str] \| None` | Organisms, each word-matched as `organism`. Omit for all. |
| `LimitParam` | `int \| None` | Max rows returned (paging). |
| `OffsetParam` | `int` | Rows to skip (paging). |
| `SummaryParam` | `bool` | True = envelope breakdowns only, no rows — the cheap first call. |
| `VerboseParam` | `bool` | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| `TreatmentTypeParam` | `list[str] \| None` | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| `BackgroundFactorsParam` | `list[str] \| None` | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| `GrowthPhasesParam` | `list[str] \| None` | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| `OmicsTypeParam` | `list[str] \| None` | Keep experiments whose omics_type is in this list. Values: list_filter_values('omics_type'). |
| `CompartmentParam` | `list[str] \| None` | Keep rows whose compartment is in this list. Values: list_filter_values('compartment'). |
| `PublicationDoisParam` | `list[str] \| None` | Restrict to these publication DOIs. |
| `MetaboliteIdsParam` | `list[str] \| None` | Metabolite IDs; bare or xref forms are coerced (see docs://analysis/metabolites). |
| `ExcludeMetaboliteIdsParam` | `list[str] \| None` | Drop these metabolites; exclude wins on overlap. |
| `InformativeOnlyParam` | `bool` | True drops terms the KG flags uninformative (roots, catch-alls). |
| `SourcesParam`, `EvidenceParam`, `MaxTierParam`, `MinEvidenceScoreParam`, `CallClassParam` | as today | the existing `_TRUST_*_DESC` texts, trimmed to ≤ 160 chars |

Check `CompartmentParam`'s current type on the 12 tools before choosing `list[str]` vs `str` — use whatever the majority is and leave any outlier for a follow-up note in the commit body (R2 lists `compartment` as a vocab filter; align only if every current use is a filter over `list[str]`).

- [ ] **Step 1: Failing test** (`tests/unit/test_params.py`):

```python
_SHARED = {
    "organism": "OrganismParam", "limit": "LimitParam", "offset": "OffsetParam",
    "summary": "SummaryParam", "verbose": "VerboseParam",
    "treatment_type": "TreatmentTypeParam", "background_factors": "BackgroundFactorsParam",
    "growth_phases": "GrowthPhasesParam", "omics_type": "OmicsTypeParam",
    "publication_dois": "PublicationDoisParam", "metabolite_ids": "MetaboliteIdsParam",
    "exclude_metabolite_ids": "ExcludeMetaboliteIdsParam", "informative_only": "InformativeOnlyParam",
    "sources": "SourcesParam", "evidence": "EvidenceParam", "max_tier": "MaxTierParam",
    "min_evidence_score": "MinEvidenceScoreParam", "call_class": "CallClassParam",
}

def test_shared_params_have_one_description_each():
    from multiomics_explorer.mcp_server import params
    schemas = _all_tool_input_schemas()
    for pname, tname in _SHARED.items():
        expected = params.__dict__[tname].__metadata__[0].description
        texts = {n: s["properties"][pname].get("description") for n, s in schemas.items() if pname in s["properties"]}
        drift = {n: t for n, t in texts.items() if t != expected}
        assert not drift, f"{pname}: {list(drift)}"
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement.** Write `params.py` with the table above. In `tools.py`, for each listed parameter on each tool replace `name: Annotated[<type>, Field(description="…")] = default` with `name: <SharedParam> = default`. Where the removed text carried a tool-specific fact (e.g. "Single-organism enforced", "inferred from locus_tags when omitted", a tool-specific `limit` default remark), move that sentence into the tool's docstring (it will be reshaped in Task 8) — do not lose it. Delete the `_TRUST_*_DESC` block from `register_tools`.

- [ ] **Step 4: Run** unit → green; docs regenerated + `--lint` clean; `git diff --stat multiomics_explorer/skills` should touch only the params tables.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/mcp_server/params.py multiomics_explorer/mcp_server/tools.py multiomics_explorer/skills tests/unit/test_params.py
git commit -m "refactor(mcp): shared Annotated param types in mcp_server/params.py (llm-review 2b.5 D3)"
```

---

### Task 8: Five-slot descriptions ≤ 600 chars + lint

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` — all 42 docstrings
- Modify: `multiomics_explorer/inputs/tools/*.yaml` — receive prose that leaves the docstrings (`mistakes` / `chaining`)
- Modify: `scripts/build_about_content.py` — new `lint_description_length(schemas)` wired into `--lint` (`:1332` area)
- Modify: `.claude/skills/layer-rules/references/layer-boundaries.md` — the template joins the outfacing-doc rules
- Test: `tests/unit/test_docs_lint.py`

**Interfaces:**
- Produces: `lint_description_length(schemas: dict) -> list[str]` returning one `"{tool}: description {n} chars > 600"` line per violation; `DESCRIPTION_MAX_CHARS = 600` module constant.

- [ ] **Step 1: Failing tests** (`tests/unit/test_docs_lint.py`):

```python
def test_lint_description_length_flags_long():
    from scripts.build_about_content import lint_description_length, DESCRIPTION_MAX_CHARS
    assert DESCRIPTION_MAX_CHARS == 600
    out = lint_description_length({"t": {"description": "x" * 601, "parameters": {}, "output_schema": None}})
    assert out == ["t: description 601 chars > 600"]
    assert lint_description_length({"t": {"description": "ok", "parameters": {}, "output_schema": None}}) == []


def test_every_tool_description_within_budget():
    from scripts.build_about_content import get_tool_schemas, lint_description_length
    assert lint_description_length(get_tool_schemas()) == []
```

(The `scripts` import path: copy how the file already imports from `build_about_content`.)

- [ ] **Step 2: Run** → first test FAILS (no function); second FAILS listing ~40 tools.

- [ ] **Step 3: Add the lint** in `scripts/build_about_content.py` next to `lint_example_yaml`:

```python
DESCRIPTION_MAX_CHARS = 600  # ≈150 tokens; spec 2b.5 D2


def lint_description_length(schemas: dict) -> list[str]:
    out = []
    for name, s in schemas.items():
        n = len(s.get("description") or "")
        if n > DESCRIPTION_MAX_CHARS:
            out.append(f"{name}: description {n} chars > {DESCRIPTION_MAX_CHARS}")
    return out
```

and in `main()` where `--lint` collects `yaml_violations`, add `desc_violations = lint_description_length(schemas)` (reuse the `get_tool_schemas()` result already computed there) and include it in the failure report.

- [ ] **Step 4: Rewrite the docstrings.** For each of the 42 tools write exactly five lines in this order (blank line after the first, as FastMCP keeps the docstring verbatim):

```
<Does>: one sentence, input → output.

Use when <question shape>; not for <adjacent need> — use `<sibling_tool>`.
Filters: <param, param, …> (names only).
Returns: <envelope keys>; one row = <what>.
docs://tools/<name>[; summary=True first for a landscape].
```

Worked example for `genes_by_ontology` (current 341 tok):

```
Gene × term pairs for ontology terms in ONE organism, with hierarchy expansion (term_ids expand down, level rolls up, both = scoped rollup).

Use to build TERM2GENE for enrichment or list a term's genes; not for a gene's own annotations — use `gene_ontology_terms`; substrate-anchored TCDB questions — use `genes_by_metabolite`.
Filters: organism, ontology, term_ids, level, tree (BRITE), min/max_gene_set_size, informative_only, sources, evidence, max_tier, min_evidence_score, call_class, interpro_type.
Returns: by_term, by_organism, gene_count stats, skipped/not_found buckets; one row = (locus_tag, term_id, evidence).
docs://tools/genes_by_ontology; summary=True first.
```

Rules while rewriting: keep every *routing* fact (sibling tool names) and every *trap* (e.g. "reactions are undirected", "recall-biased, not DE") — a trap that no longer fits goes verbatim into the tool's YAML `mistakes` list; keep `[AQ]` / `[TRUST]`-style facts only as the pointer to the docs page; never introduce dates or changelog words. Work tool by tool in the order of the size table in the spec (largest first); run the two lint tests after every ~8 tools.

- [ ] **Step 5: Layer-boundaries text.** In `.claude/skills/layer-rules/references/layer-boundaries.md`, under the outfacing-doc rules, add rule 10:

```
10. Tool docstring = five slots, ≤ 600 chars (lint `lint_description_length`):
    Does / Use when–not when (name the sibling tool) / Filters (names only) /
    Returns (envelope keys + one row) / docs://tools/{name} pointer. Semantics of
    a parameter live in its Field description; traps live in the YAML `mistakes`.
```

- [ ] **Step 6: Run** `uv run pytest tests/unit -q -p no:cacheprovider` → green; `uv run python scripts/build_about_content.py && uv run python scripts/build_about_content.py --lint` → clean; `uv run python scripts/refresh_examples.py --check` → no `error`; measure: the spec's size script (`sum(len(t.description) for t in await mcp.list_tools()) // 4`) reports ≤ 6300.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py multiomics_explorer/inputs/tools multiomics_explorer/skills scripts/build_about_content.py tests/unit/test_docs_lint.py .claude/skills/layer-rules/references/layer-boundaries.md
git commit -m "docs(mcp): five-slot tool descriptions <=600 chars with lint (llm-review 2b.5 D2)"
```

---

### Task 9: Naming-rule contract test, layer-rules text, CHANGELOG, regression + live check

**Files:**
- Create: `tests/unit/test_param_naming_rules.py`
- Modify: `.claude/skills/layer-rules/SKILL.md` (Layer 3)
- Modify: `CHANGELOG.md` (`[Unreleased]` → `Breaking` + `Changed`)
- Modify: `docs/backlog.md` (delete row 2b.5)

**Interfaces:**
- Consumes: `_all_tool_input_schemas()` helper from `tests/unit/test_tool_wrappers.py` (import it or move it to `tests/unit/_mcp_helpers.py` and import from both).

- [ ] **Step 1: Write the contract test** (`tests/unit/test_param_naming_rules.py`):

```python
"""Layer-3 parameter naming rules R1-R4 (spec 2026-08-30 llm-review 2b.5), checked on tools/list."""
import re
import pytest
from tests.unit.test_tool_wrappers import _all_tool_input_schemas

SCHEMAS = _all_tool_input_schemas()
ALL_PARAMS = {(tool, p): prop for tool, s in SCHEMAS.items() for p, prop in s["properties"].items()}
VOCAB = {"treatment_type", "background_factors", "growth_phases", "omics_type", "compartment"}
# Names that legitimately break a rule (each with the reason kept in the spec).
ALLOW = {"organism", "organisms", "source", "sources", "analysis_id", "analysis_ids", "categories"}


def _is_list(prop):
    if prop.get("type") == "array":
        return True
    return any(_is_list(x) for x in prop.get("anyOf", []))


def test_r1_ranges_are_min_max_prefixed():
    bad = [p for (_, p) in ALL_PARAMS if re.search(r"_(min|max)$", p)]
    assert bad == [], bad


def test_r2_vocab_filters_are_lists_named_by_property():
    bad = [(t, p) for (t, p), prop in ALL_PARAMS.items() if p in VOCAB and not _is_list(prop)]
    assert bad == [], bad
    assert not any(p == "treatment_types" for (_, p) in ALL_PARAMS)


def test_r3_id_batches_are_plural():
    bad = [(t, p) for (t, p), prop in ALL_PARAMS.items()
           if _is_list(prop) and re.search(r"_(id|doi|tag)$", p) and p not in ALLOW]
    assert bad == [], bad


def test_r4_filters_match_row_fields():
    for tool, p in (("genes_by_numeric_metric", "bucket"), ("genes_by_boolean_metric", "flag"), ("genes_by_function", "category")):
        assert (tool, p) not in ALL_PARAMS, (tool, p)
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_param_naming_rules.py -q -p no:cacheprovider` → PASS (Tasks 3–6 already made it true; if anything fails, the earlier task missed a tool — fix there).

- [ ] **Step 3: Layer-rules text.** In `.claude/skills/layer-rules/SKILL.md` Layer 3, after the shared-param sentence added in Task 1, add:

```
Parameter names (tests/unit/test_param_naming_rules.py enforces):
R1 ranges are `min_x` / `max_x`; R2 vocabulary filters use the KG property
name typed `list[str]`; R3 ID batches are plural (`locus_tags`, `publication_dois`);
R4 a filter is named after the row field it filters (`metric_bucket`, `flag_value`).
Shared params come from `mcp_server/params.py` — never re-describe `organism`,
`limit`, `summary`, trust filters etc. inline. Python-API renames keep the old
keyword one release via `api/_compat.deprecated_alias`; MCP schemas never carry aliases.
```

- [ ] **Step 4: CHANGELOG.** Under `[Unreleased]` add a `### Breaking` block listing every rename from Tasks 3–6 as `old → new (tool[s])`, one line each, plus "`outputSchema` no longer emitted on `tools/list`"; under `### Changed`: "tool descriptions ≤ 600 chars (five-slot template); shared parameter descriptions". Delete row 2b.5 from `docs/backlog.md` §1.

- [ ] **Step 5: Full verification.**
  - `uv run pytest tests/unit -q -p no:cacheprovider` → green.
  - `uv run pytest -m kg -q -p no:cacheprovider` → green (needs the live KG).
  - Regression: run the project's golden regeneration (`grep -n "force-regen" scripts/*.py tests/*.py .claude/skills/*/SKILL.md` for the exact command) with `--force-regen`, then `git status --short tests/` → **no golden changed**. Any diff = a response-shape change, which this plan forbids — find the task that caused it and revert that part.
  - `uv run python scripts/build_about_content.py --lint` → clean; `uv run python scripts/refresh_examples.py --check` → no `error`.
  - Research repo: `grep -rn "publication_doi=\|value_min\|mass_min\|bucket=\|flag=\|treatment_types=\|rank_by_metric_max\|metric_percentile_m" /home/osnat/github/multiomics_research --include=*.py --include=*.yaml --include=*.md` → only hits that are not explorer calls.
  - Live: ask the user to `/mcp` restart, then call `mcp__multiomics-kg__genes_by_numeric_metric` with `metric_bucket` and `mcp__multiomics-kg__list_publications` with `treatment_type=["coculture"]`; both succeed and `tools/list` shows no `outputSchema`.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_param_naming_rules.py .claude/skills/layer-rules/SKILL.md CHANGELOG.md docs/backlog.md
git commit -m "test(mcp): parameter naming-rule contract; layer-rules + CHANGELOG for 2b.5"
```

Then hand off via `superpowers:finishing-a-development-branch` (merge to `main` locally; no push).
