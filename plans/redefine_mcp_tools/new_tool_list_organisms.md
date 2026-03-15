# Plan: `list_organisms` Tool

New MCP tool — returns all organisms in the KG with metadata. Helps the LLM
construct valid `organism` filters without guessing or burning a `run_cypher` call.

**Caching:** Results change only on KG rebuild (~18 rows, stable). Cache in
lifespan context on first call and return the cached value on subsequent calls.

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

## Agent assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1 | **query-builder** | Add `build_list_organisms` to `queries_lib.py` | — |
| 2 | **tool-wrapper** | Add `list_organisms` tool to `tools.py` with caching | query-builder |
| 3a | **test-updater** | Add unit, integration, eval, and regression tests | tool-wrapper |
| 3b | **doc-updater** | Update `CLAUDE.md`, `README.md`, `AGENT.md`, `docs/testplans/testplan.md` | tool-wrapper |
| 4 | **code-reviewer** | Review all changes against this plan, run unit tests, grep for stale refs | test-updater, doc-updater |

Steps 3a and 3b can run in parallel.

## Query builders

**Files:** `queries_lib.py`

### `build_list_organisms`

```cypher
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o)
RETURN o.preferred_name AS name, o.genus AS genus,
       o.strain_name AS strain, o.clade AS clade,
       count(g) AS gene_count
ORDER BY o.genus, o.preferred_name
```

Returns ~18 rows. Small, stable, cacheable.

No fixture updates needed — this tool returns organisms, not genes, so
`tests/fixtures/gene_data.py` is unaffected.

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**
- Verify Cypher structure (MATCH OrganismTaxon, OPTIONAL MATCH Gene)
- No parameters needed — builder takes no args

**`tests/unit/test_tool_wrappers.py`:**
- Mock query results, verify JSON response structure
- Verify all expected columns: `name`, `genus`, `strain`, `clade`, `gene_count`
- Empty result returns appropriate message (no organisms found)
- Tool registration count bumps from 9 to 10

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
    row0:
      genus: Alteromonas

- id: list_organisms_raw
  tool: raw_cypher
  desc: Snapshot of all organisms with metadata
  params:
    query: >
      MATCH (o:OrganismTaxon)
      OPTIONAL MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o)
      RETURN o.preferred_name AS name, o.genus AS genus,
             o.strain_name AS strain, o.clade AS clade,
             count(g) AS gene_count
      ORDER BY o.genus, o.preferred_name
  expect:
    min_rows: 10
    columns: [name, genus, strain, clade, gene_count]
    contains:
      name: Prochlorococcus MED4
```

### Regression snapshots (`tests/regression/`)

The `raw_cypher` eval case above automatically produces a regression baseline.
This snapshot is particularly valuable — it detects if an organism is
accidentally dropped or added during KG rebuilds.

```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```

## Documentation updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add `list_organisms` row to MCP Tools table |
| `README.md` | Add entry to MCP tools section, bump tool count |
| `AGENT.md` | Add row to tools table |
| `docs/testplans/testplan.md` | Add `list_organisms` test plan section (see below) |
| `.claude/skills/update-tests/SKILL.md` | Update test counts after implementation |

### Test plan section (`docs/testplans/testplan.md`)

Append after the `list_filter_values` section:

---

### `list_organisms` Tool Tests

#### Unit tests (`tests/unit/test_query_builders.py`)
- [ ] `build_list_organisms`: verify Cypher structure (MATCH OrganismTaxon, OPTIONAL MATCH Gene)

#### Unit tests (`tests/unit/test_tool_wrappers.py`)
- [ ] Returns JSON array with expected columns
- [ ] All expected columns: `name`, `genus`, `strain`, `clade`, `gene_count`
- [ ] Empty result handling
- [ ] Tool registration count updated (9 → 10)

#### Integration tests (`tests/integration/test_tool_correctness_kg.py`)
- [ ] Known organisms present: MED4, MIT9313, EZ55, HOT1A3
- [ ] `gene_count > 0` for strains with genes
- [ ] `clade` populated for Prochlorococcus strains
- [ ] `clade` is null for Alteromonas/Synechococcus

#### Eval cases (`tests/evals/cases.yaml`)
- [ ] `list_organisms` — tool-level response
- [ ] `list_organisms_raw` — raw_cypher snapshot of all organisms
