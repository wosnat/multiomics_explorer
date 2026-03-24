# Test checklist — per-layer patterns

## Query builder tests (`tests/unit/test_query_builders.py`)

### Class naming

`class TestBuild{Name}:` — matches the builder function name.

### Minimal test set

```python
class TestBuildNewTool:
    def test_basic(self):
        """Call with required params, assert Cypher and params."""
        cypher, params = build_new_tool(required_param="value")
        assert "MATCH" in cypher
        assert params["required_param"] == "value"

    def test_returns_expected_columns(self):
        """All RETURN columns present in Cypher."""
        cypher, _ = build_new_tool(required_param="x")
        for col in ["locus_tag", "gene_name", "product"]:
            assert col in cypher

    def test_with_optional_param(self):
        """Optional param appears in Cypher/params when provided."""
        cypher, params = build_new_tool(
            required_param="x", optional_param="filter_value"
        )
        assert params["optional_param"] == "filter_value"
        # assert the WHERE clause references it

    def test_verbose_adds_columns(self):
        """verbose=True adds heavy text columns."""
        cypher_compact, _ = build_new_tool(required_param="x")
        cypher_verbose, _ = build_new_tool(required_param="x", verbose=True)
        assert "heavy_text_field" not in cypher_compact
        assert "heavy_text_field" in cypher_verbose

    def test_order_by(self):
        cypher, _ = build_new_tool(required_param="x")
        assert "ORDER BY" in cypher

    def test_invalid_enum_raises(self):
        """Invalid enum value raises ValueError in builder."""
        with pytest.raises(ValueError, match="invalid"):
            build_new_tool(required_param="x", enum_param="bad_value")
```

### UNWIND variable scoping

For builders that use `UNWIND $list AS var` (summary builders, verbose
detail builders), test that `var` survives `WITH DISTINCT` clauses.
This catches a class of bug where WITH DISTINCT drops variables from
scope — only detectable against a live DB without this test.

```python
def test_tid_survives_with_distinct(self):
    """UNWIND-based query must carry tid through WITH DISTINCT."""
    cypher, _ = build_tool_summary(ontology="go_bp", term_ids=["go:0006260"])
    for line in cypher.split("\n"):
        if "WITH DISTINCT" in line and "descendant" in line:
            assert "tid" in line, f"tid dropped from scope: {line}"
```

Parametrize across all ontology types (hierarchy + flat) since flat
ontologies use `WITH root AS descendant` which is especially prone
to dropping variables.

### Assert patterns

- `assert "keyword" in cypher` — check Cypher structure
- `assert params["key"] == value` — check parameter passing
- `assert "keyword" not in cypher` — check optional clause absent
- No mock needed — builders are pure functions

---

## API function tests (`tests/unit/test_api_functions.py`)

### Class naming

`class TestNewTool:` — matches the API function name.

### Fixture

```python
@pytest.fixture()
def mock_conn():
    return MagicMock()
```

### Minimal test set

```python
class TestNewTool:
    def test_returns_dict_with_results(self, mock_conn):
        """API returns dict with summary fields + results list."""
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN"}
        ]
        result = api.new_tool("param", conn=mock_conn)
        assert isinstance(result, dict)
        assert "results" in result
        assert "total_matching" in result
        assert "returned" in result
        assert "truncated" in result
        assert result["results"][0]["locus_tag"] == "PMM0001"

    def test_empty_results(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.new_tool("param", conn=mock_conn)
        assert result["results"] == []
        assert result["total_matching"] == 0
        assert result["returned"] == 0
        assert result["truncated"] is False

    def test_limit_caps_results(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": f"PMM{i:04d}"} for i in range(20)
        ]
        result = api.new_tool("param", limit=5, conn=mock_conn)
        assert result["total_matching"] == 20
        assert result["returned"] == 5
        assert result["truncated"] is True
        assert len(result["results"]) == 5

    def test_summary_returns_empty_results(self, mock_conn):
        """summary=True returns results=[] with summary fields."""
        mock_conn.execute_query.return_value = [...]  # summary query result
        result = api.new_tool("param", summary=True, conn=mock_conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True

    def test_invalid_param_raises(self, mock_conn):
        with pytest.raises(ValueError, match="must not be empty"):
            api.new_tool("", conn=mock_conn)
```

### Batch tool tests (tools accepting ID lists)

```python
class TestBatchTool:
    def test_not_found_field(self, mock_conn):
        """Batch tools include not_found for missing IDs."""
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN"}
        ]
        result = api.batch_tool(
            locus_tags=["PMM0001", "FAKE999"], conn=mock_conn)
        assert "not_found" in result
        assert "FAKE999" in result["not_found"]
        assert len(result["results"]) == 1

    def test_all_found(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001"}, {"locus_tag": "PMM0002"}
        ]
        result = api.batch_tool(
            locus_tags=["PMM0001", "PMM0002"], conn=mock_conn)
        assert result["not_found"] == []
```

### Multi-query functions (2-query pattern)

```python
# Summary query returns first, detail query returns second
mock_conn.execute_query.side_effect = [summary_result, detail_result]
```

### Lucene retry test

```python
from neo4j.exceptions import ClientError as Neo4jClientError

def test_lucene_retry(self, mock_conn):
    mock_conn.execute_query.side_effect = [
        Neo4jClientError("Failed to invoke ..."),
        [{"locus_tag": "PMM0001"}],
    ]
    result = api.search_tool("query+with+special", conn=mock_conn)
    assert len(result["results"]) == 1
    assert mock_conn.execute_query.call_count == 2
```

---

## MCP wrapper tests (`tests/unit/test_tool_wrappers.py`)

### Fixtures (module-scoped)

```python
@pytest.fixture(scope="module")
def tool_fns():
    mcp = FastMCP("test")
    register_tools(mcp)
    return {name: t.fn for name, t in mcp._tool_manager._tools.items()}

@pytest.fixture()
def mock_ctx():
    ctx = MagicMock()
    ctx.request_context.lifespan_context.conn = MagicMock()
    return ctx

def _conn_from(ctx):
    return ctx.request_context.lifespan_context.conn
```

### Class naming

`class TestNewToolWrapper:` — tool name + "Wrapper".

### Minimal test set (v3 pattern — Pydantic response models)

```python
class TestNewToolWrapper:
    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        """Wrapper returns Pydantic response model."""
        _conn_from(mock_ctx).execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN"}
        ]
        result = await tool_fns["new_tool"](mock_ctx, param="value")
        assert hasattr(result, "results")
        assert hasattr(result, "total_matching")
        assert hasattr(result, "returned")
        assert hasattr(result, "truncated")

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = await tool_fns["new_tool"](mock_ctx, param="value")
        assert result.results == []
        assert result.returned == 0

    @pytest.mark.asyncio
    async def test_default_limit_is_small(self, tool_fns, mock_ctx):
        """MCP default limit should be small (e.g. 5)."""
        _conn_from(mock_ctx).execute_query.return_value = [
            {"locus_tag": f"PMM{i:04d}"} for i in range(20)
        ]
        result = await tool_fns["new_tool"](mock_ctx, param="x")
        assert result.returned <= 5  # default limit

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from api/ becomes ToolError."""
        _conn_from(mock_ctx).execute_query.side_effect = ValueError("bad")
        with pytest.raises(ToolError):
            await tool_fns["new_tool"](mock_ctx, param="x")

    @pytest.mark.asyncio
    async def test_unexpected_error_raises_tool_error(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.side_effect = RuntimeError("boom")
        with pytest.raises(ToolError):
            await tool_fns["new_tool"](mock_ctx, param="x")
```

### Important: update EXPECTED_TOOLS

```python
EXPECTED_TOOLS = [
    "kg_schema", "list_filter_values", "list_organisms", "resolve_gene",
    "genes_by_function", "gene_overview",
    "gene_homologs", "run_cypher",
    "search_ontology", "genes_by_ontology", "gene_ontology_terms",
    "list_publications", "list_experiments",
    # New tools as they're built:
    # "search_homolog_groups", "genes_by_homolog_group",
    # "differential_expression_by_gene", "differential_expression_by_ortholog",
]
```

**Note:** The list above shows the **target** names after v3 migration.
During transition, old names remain until each tool is renamed.
Current names: `get_schema`, `search_genes`, `get_gene_details`,
`get_homologs`.

---

## Integration tests

### Correctness (`tests/integration/test_tool_correctness_kg.py`)

- Mark: `@pytest.mark.kg` on class
- Uses `conn` fixture from `conftest.py` (session-scoped, auto-skips)
- Gene fixtures: `GENES`, `GENES_BY_LOCUS`, `GENES_WITH_GENE_NAME`
- Character escaping: `_kg_escape()` for text comparisons

### Smoke tests (`tests/integration/test_mcp_tools.py`)

- Quick validation that tools return valid results against live KG
- Less detailed assertions than correctness tests

### API contract (`tests/integration/test_api_contract.py`)

- Verifies API function return types and key presence against live KG
- Check `result` is `dict`, has `results` key, has `total_matching`/`returned`/`truncated`

---

## Regression tests

See [regression guide](regression-guide.md) for golden-file tests.

### TOOL_BUILDERS dict

Maps tool/case names to query builder functions. Uses **target** names
after v3 migration (update as tools are renamed):

```python
TOOL_BUILDERS = {
    "resolve_gene": build_resolve_gene,
    "genes_by_function": build_genes_by_function,  # was: search_genes
    "gene_overview": build_gene_overview,
    "gene_homologs": ...,  # was: get_homologs (multi-step)
    # Per-ontology partial entries
    "search_ontology_go_bp": partial(build_search_ontology, ontology="go_bp"),
    # ...
}
```

**Note:** During transition, old builder names remain until renamed.
