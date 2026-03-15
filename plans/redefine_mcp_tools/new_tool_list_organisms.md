# Plan: `list_organisms` Tool

New MCP tool — returns all organisms in the KG with metadata. Helps the LLM
construct valid `organism` filters without guessing or burning a `run_cypher` call.

## Tool signature

```python
@mcp.tool()
def list_organisms(ctx: Context) -> str:
    """List all organisms in the knowledge graph with strain, genus, clade,
    and gene count.

    Use this to discover valid organism names for filtering in other tools.
    The organism filter uses partial matching (CONTAINS), so "MED4",
    "Prochlorococcus MED4", and "Prochlorococcus" all work.
    """
```

## Query builder — `build_list_organisms`

**Files:** `queries_lib.py`

```cypher
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o)
RETURN o.preferred_name AS name, o.genus AS genus,
       o.strain_name AS strain, o.clade AS clade,
       count(g) AS gene_count
ORDER BY o.genus, o.preferred_name
```

Returns ~18 rows. Small, stable, cacheable.

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**
- Verify Cypher structure (MATCH OrganismTaxon, OPTIONAL MATCH Gene)
- No parameters needed — builder takes no args

**`tests/unit/test_tool_wrappers.py`:**
- Mock query results, verify JSON response structure
- Verify all expected columns: `name`, `genus`, `strain`, `clade`, `gene_count`

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

- Verify known organisms returned (MED4, MIT9313, EZ55, HOT1A3, etc.)
- Verify `gene_count > 0` for strains with genes
- Verify `clade` populated for Prochlorococcus strains (HLI, HLII, LLII, LLIV)
- Verify `clade` is null for Alteromonas/Synechococcus

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: list_organisms
  tool: list_organisms
  desc: Returns all organisms with metadata
  params: {}
  expect:
    min_rows: 10
    columns: [name, genus, strain, clade, gene_count]
    contains:
      name: Prochlorococcus MED4
```

### Regression snapshots (`tests/regression/`)

Add `list_organisms` to `TOOL_BUILDERS` in `tests/regression/test_regression.py`.
Since the builder takes no params, the eval case uses `params: {}`.

```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```

This snapshot is particularly valuable — it detects if an organism is
accidentally dropped or added during KG rebuilds.
