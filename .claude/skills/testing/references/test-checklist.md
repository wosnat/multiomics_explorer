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

    def test_order_by(self):
        cypher, _ = build_new_tool(required_param="x")
        assert "ORDER BY" in cypher

    def test_invalid_enum_raises(self):
        """Invalid enum value raises ValueError in builder."""
        with pytest.raises(ValueError, match="invalid"):
            build_new_tool(required_param="x", enum_param="bad_value")
```

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
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN"}
        ]
        result = api.new_tool("param", conn=mock_conn)
        assert isinstance(result, list)
        assert result[0]["locus_tag"] == "PMM0001"

    def test_empty_results(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.new_tool("param", conn=mock_conn)
        assert result == []

    def test_invalid_param_raises(self, mock_conn):
        with pytest.raises(ValueError, match="must not be empty"):
            api.new_tool("", conn=mock_conn)

    def test_conn_defaults(self):
        """Function creates connection if None provided."""
        # Usually tested implicitly; explicit test if needed
```

### Multi-query functions

```python
mock_conn.execute_query.side_effect = [result1, result2]
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
    assert len(result) == 1
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

### Minimal test set

```python
class TestNewToolWrapper:
    def test_returns_json(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN"}
        ]
        result = tool_fns["new_tool"](mock_ctx, param="value")
        parsed = json.loads(result)
        assert len(parsed) >= 1

    def test_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["new_tool"](mock_ctx, param="value")
        # Check for appropriate empty message
        assert "No" in result or result == "[]"

    def test_limit_capped(self, tool_fns, mock_ctx):
        """Limit is capped at max value."""
        _conn_from(mock_ctx).execute_query.return_value = [
            {"locus_tag": f"PMM{i:04d}"} for i in range(100)
        ]
        result = tool_fns["new_tool"](mock_ctx, param="x", limit=999)
        parsed = json.loads(result)
        assert len(parsed) <= 50  # or whatever the tool's max is

    def test_error_returns_string(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.side_effect = ValueError("bad input")
        result = tool_fns["new_tool"](mock_ctx, param="x")
        assert "Error" in result
```

### Important: update EXPECTED_TOOLS

```python
EXPECTED_TOOLS = [
    "get_schema", "list_filter_values", "list_organisms", "resolve_gene",
    "search_genes", "gene_overview", "get_gene_details",
    "get_homologs", "run_cypher",
    "search_ontology", "genes_by_ontology", "gene_ontology_terms",
    # Add new tool here
]
```

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
