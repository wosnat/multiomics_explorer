# Code review checklist

## Layer 1: `kg/queries_lib.py`

- [ ] Builder uses keyword-only args (after `*`)?
- [ ] Returns `tuple[str, dict]`?
- [ ] No `conn` parameter?
- [ ] No imports from `api/` or `mcp_server/`?
- [ ] No `conn.execute_query` calls?
- [ ] No JSON formatting?
- [ ] No logging?
- [ ] All user inputs use `$param` placeholders (no f-string interpolation)?
- [ ] RETURN columns use `AS snake_case` aliases?
- [ ] `ORDER BY` clause for deterministic results?
- [ ] Organism filter uses `ALL(word IN split(toLower($organism), ' ') ...)`?
- [ ] Optional params use NULL-safe pattern (`$param IS NULL OR ...`)?
- [ ] Summary builder is a separate function (not mode logic in builder)?

## Layer 2: `api/functions.py`

- [ ] `conn: GraphConnection | None = None` as keyword-only last param?
- [ ] Uses `_default_conn(conn)` at function start?
- [ ] Returns `dict` with summary fields + `results` list (no strings, no JSON)?
- [ ] Assembles complete response dict (summary fields, `returned`, `truncated`, `not_found` for batch tools)? MCP must not compute these.
- [ ] `summary=True` sets `limit=0`?
- [ ] 2-query pattern: summary query always runs, detail query skipped when `limit=0`?
- [ ] Batch tools (accept ID lists) include `not_found` field?
- [ ] No JSON formatting?
- [ ] No imports from `mcp_server/`?
- [ ] Validates inputs, raises `ValueError` with specific messages?
- [ ] Fulltext queries use Lucene retry pattern?
- [ ] Docstring lists return dict keys?
- [ ] Added to `api/__init__.py` `__all__`?
- [ ] Re-exported from `multiomics_explorer/__init__.py` `__all__`?

## Layer 3: `mcp_server/tools.py`

- [ ] `@mcp.tool()` inside `register_tools(mcp)`?
- [ ] `ctx: Context` as first parameter?
- [ ] Calls `api/` functions (not `queries_lib` directly)?
- [ ] Catches `ValueError` → `raise ToolError(str(e))`?
- [ ] Catches `Exception` → `raise ToolError(f"Error in {tool_name}: {e}")`?
- [ ] Uses `ToolError` for errors (not error strings)?
- [ ] `async def` tool function?
- [ ] `await ctx.info()` at entry with key params?
- [ ] `await ctx.warning()` on ValueError, `await ctx.error()` on Exception?
- [ ] Uses `Annotated[type, Field(description=...)]` for all params?
- [ ] Uses `Field(ge=..., le=...)` for numeric constraints?
- [ ] `tags` and `annotations={"readOnlyHint": True}` set?
- [ ] Docstring is tool-level purpose (no `Args:` — descriptions in Field)?
- [ ] Docstring mentions related tools for chaining?
- [ ] Return schema is in Pydantic models (not duplicated in docstring)?
- [ ] Pydantic response models defined (`{Name}Result` + `{Name}Response`)?
- [ ] `{Name}Result` fields have `Field(description=...)` with examples on all fields?
- [ ] Return type annotation is the response model (→ auto outputSchema)?
- [ ] No field computation — api/ dict → `Response(**data)`?
- [ ] Does NOT mutate `data` dict in-place (construct models into new vars, not `data["field"] = ...`)?
- [ ] Default `limit` is small (e.g. 5) — not 50 or 100?
- [ ] Empty results return model with `results=[]` (not ToolError)?

## Layer 4: Skills (MCP resources)

- [ ] Input YAML exists at `inputs/tools/{name}.yaml`?
- [ ] About content built via `scripts/build_about_content.py {name}`?
- [ ] About content auto-generated from Pydantic + YAML (not hand-written)?
- [ ] Params table, response format, expected keys match current Pydantic models?
- [ ] Chaining patterns documented?
- [ ] Common mistakes section if applicable?
- [ ] `pytest tests/unit/test_about_content.py` passes (consistency)?
- [ ] `pytest tests/integration/test_about_examples.py` passes (examples execute)?
- [ ] `Literal`/enum params show valid values in Parameters table (not bare `string`)?
- [ ] Example-response result objects on single lines (multi-line objects cause key-extraction regex to match nested fields as top-level)?

## Cross-layer consistency

- [ ] Parameter names match across all 3 code layers (`summary`, `verbose`,
      `limit` — same names at api/ and MCP)?
- [ ] ID params are lists (`locus_tags`, `experiment_ids`, `group_ids`)
      — no singular forms?
- [ ] Return field names match between Cypher RETURN, API docstring,
      and about content `expected-keys`?
- [ ] MCP tool name matches API function name?
- [ ] Builder name follows `build_{api_function_name}` pattern?
- [ ] Default values consistent across layers?
- [ ] About content example calls use correct param names for other
      tools referenced in chaining examples?
- [ ] For renames: other tools' docstrings that reference the old name
      updated? (grep for old name across all `.py` files)

## Tools with rich summary fields

- [ ] Unified response model — summary fields + results in same dict/type?
- [ ] `summary=True` → `limit=0` → `results=[]`, `returned=0`, `truncated=(total_matching > 0)`?
- [ ] Summary fields always populated (both when summary=True and False)?
- [ ] 2-query pattern: summary query always runs, detail skipped when `limit=0`?
- [ ] Summary query uses `apoc.coll.frequencies` for breakdowns?
- [ ] API renames `{item, count}` to domain keys, sorts descending?
- [ ] Fulltext tools include `score_max`/`score_median` in summary fields?

## Precomputed stats / sentinel values

- [ ] If reading Neo4j array properties, handle sentinel values?
      (`""` → None for labels, `-1.0` → None for hours)
- [ ] Non-applicable fields omitted (e.g. time_points for non-time-course)?

## List-type filter params

- [ ] `list[str] | None` for exact-match multi-value filters?
- [ ] Case normalization in Python before Cypher `IN` clause?
- [ ] CONTAINS filters stay as single `str`?

## Test coverage

- [ ] `TestBuild{Name}` class in `test_query_builders.py`?
- [ ] `Test{Name}` class in `test_api_functions.py`?
- [ ] `Test{Name}Wrapper` class in `test_tool_wrappers.py`?
- [ ] Tool in `EXPECTED_TOOLS` list?
- [ ] Builder in `TOOL_BUILDERS` dict?
- [ ] Eval cases in `cases.yaml`?
- [ ] Integration tests if tool touches new data?
- [ ] Contract tests (`test_api_contract.py`) updated if return shape changed?
- [ ] Regression baselines regenerated if columns/tool renamed? (`--force-regen`)
- [ ] Tests for every optional parameter?
- [ ] Tests for validation errors?
- [ ] Tests for empty results?

## Naming conventions

- [ ] Return field names use standard names where applicable?
      (`locus_tag`, `gene_name`, `product`, `organism_strain`, `score`)
- [ ] New parameter names follow existing conventions?
      (`organism`, `search_text`, `ontology`, `category`, `limit`, `summary`, `verbose`)
- [ ] Test class naming follows conventions?
      (`TestBuild{Name}`, `Test{Name}`, `Test{Name}Wrapper`)

## Cypher safety

- [ ] No write keywords in read-only queries?
- [ ] User input never interpolated into Cypher strings?
- [ ] Parameters passed via `$param` only?
- [ ] If using `CALL db.index.fulltext.queryNodes`, search text is parameterized?
