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
- [ ] Returns `list[dict]` or `dict` (no strings, no JSON)?
- [ ] No display limits (callers slice)?
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
- [ ] Docstring documents return envelope fields?
- [ ] Docstring mentions related tools for chaining?
- [ ] Pydantic response models defined (`{Name}Result` + `{Name}Response`)?
- [ ] `{Name}Result` fields have `Field(description=...)` on non-obvious fields?
- [ ] Return type annotation is the response model (→ auto outputSchema)?
- [ ] Returns model instances (not dicts)?
- [ ] Empty results return model with `results=[]` (not ToolError)?

## Layer 4: Skills (MCP resources)

- [ ] Input YAML exists at `inputs/tools/{name}.yaml`?
- [ ] About content built via `scripts/build_about_content.py {name}`?
- [ ] Content includes `example-call` and `expected-keys` tagged blocks?
- [ ] `expected-keys` match actual tool return fields?
- [ ] Chaining patterns documented?
- [ ] Common mistakes section if applicable?
- [ ] `pytest tests/unit/test_about_content.py` passes (consistency)?
- [ ] `pytest tests/integration/test_about_examples.py` passes (examples execute)?

## Cross-layer consistency

- [ ] Parameter names match across all 3 code layers?
- [ ] Return field names match between Cypher RETURN, API docstring,
      and about content `expected-keys`?
- [ ] MCP tool name matches API function name?
- [ ] Builder name follows `build_{api_function_name}` pattern?
- [ ] Default values consistent across layers?

## Test coverage

- [ ] `TestBuild{Name}` class in `test_query_builders.py`?
- [ ] `Test{Name}` class in `test_api_functions.py`?
- [ ] `Test{Name}Wrapper` class in `test_tool_wrappers.py`?
- [ ] Tool in `EXPECTED_TOOLS` list?
- [ ] Builder in `TOOL_BUILDERS` dict?
- [ ] Eval cases in `cases.yaml`?
- [ ] Integration tests if tool touches new data?
- [ ] Tests for every optional parameter?
- [ ] Tests for validation errors?
- [ ] Tests for empty results?

## Naming conventions

- [ ] Return field names use standard names where applicable?
      (`locus_tag`, `gene_name`, `product`, `organism_strain`, `score`)
- [ ] New parameter names follow existing conventions?
      (`organism`, `search_text`, `ontology`, `category`, `limit`, `mode`)
- [ ] Test class naming follows conventions?
      (`TestBuild{Name}`, `Test{Name}`, `Test{Name}Wrapper`)

## Cypher safety

- [ ] No write keywords in read-only queries?
- [ ] User input never interpolated into Cypher strings?
- [ ] Parameters passed via `$param` only?
- [ ] If using `CALL db.index.fulltext.queryNodes`, search text is parameterized?
