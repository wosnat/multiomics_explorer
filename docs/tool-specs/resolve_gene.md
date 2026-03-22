# Tool spec: resolve_gene

## Purpose

Resolve a gene identifier (locus_tag, gene name, old locus tag, RefSeq
protein ID) to matching Gene nodes in the KG. This is the entry point
for gene-specific workflows — downstream tools require locus_tags.

## Out of Scope

- Gene functional details — that's `gene_overview` or `get_gene_details`
- Free-text search across annotations — that's `search_genes`

## Status / Prerequisites

- [x] KG spec complete: `docs/kg-specs/kg-spec-resolve-gene.md`
- [x] No KG changes needed
- [ ] Ready for Phase 2 (build)

## Use cases

- **Lookup by locus_tag:** "Resolve PMM0001" → confirms it exists, shows
  organism and product
- **Lookup by gene name:** "Resolve dnaN" → returns all organisms with a
  dnaN gene, grouped by organism
- **Lookup by old ID:** "Resolve WP_011132082.1" → finds gene via
  all_identifiers cross-reference
- **Scoped lookup:** "Resolve dnaN in MED4" → organism filter narrows
  to one strain
- **Chaining:** `resolve_gene` → `gene_overview(gene_ids=[...])` →
  `get_homologs(locus_tag=...)` or `gene_ontology_terms(gene_id=...)`

## KG dependencies

- `Gene` nodes: locus_tag, gene_name, product, organism_strain,
  all_identifiers
- KG spec: `docs/kg-specs/kg-spec-resolve-gene.md`

---

## Result-size controls

Always small (a gene name matches at most ~15 organisms). No modes needed.

**`limit`** (int, default 50): Cap results for safety. Result set is
small today but could grow with more genomes.

No `verbose` — all fields are lightweight.
No summary/detail modes — result set never large.

**Sort key:** `organism_strain ASC, locus_tag ASC`

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes", "discovery"},
    annotations={"readOnlyHint": True},
)
async def resolve_gene(
    ctx: Context,
    identifier: Annotated[str, Field(
        description="Gene identifier (case-insensitive) — locus_tag "
        "(e.g. 'PMM0001'), gene name (e.g. 'dnaN'), old locus tag, "
        "or RefSeq protein ID.",
    )],
    organism: Annotated[str | None, Field(
        description="Filter by organism (case-insensitive partial match). "
        "E.g. 'MED4', 'Prochlorococcus MED4'.",
    )] = None,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 50,
) -> ResolveGeneResponse:
    """Resolve a gene identifier to matching genes in the knowledge graph.

    Matching is case-insensitive — 'pmm0001', 'PMM0001', and 'Pmm0001'
    all work. Use the returned locus_tags with gene_overview,
    get_gene_details, get_homologs, or gene_ontology_terms. The organism
    filter uses case-insensitive partial matching — 'MED4' and
    'Prochlorococcus MED4' both work.
    """
```

---

## Response envelope

Flat list sorted by organism_strain, locus_tag (consistent with v2 tools):

**ResolveGeneResponse:**

| Field | Type | Description |
|---|---|---|
| total_matching | int | Total genes matching identifier + organism filter (e.g. 3) |
| returned | int | Genes in this response (e.g. 3) |
| truncated | bool | True if total_matching > returned |
| results | list[GeneMatch] | Matching genes sorted by organism_strain, locus_tag |

No `total_entries` — this is a per-identifier lookup, not a browsable
collection. There's no "all genes in KG" denominator.

**GeneMatch:**

| Field | Type | Description |
|---|---|---|
| locus_tag | str | Gene locus tag (e.g. "PMM0001") |
| gene_name | str\|null | Gene name (e.g. "dnaN") |
| product | str\|null | Gene product (e.g. "DNA polymerase III, beta subunit") |
| organism_strain | str | Organism (e.g. "Prochlorococcus MED4") |

### Empty results

- No matches → `ResolveGeneResponse(total_matching=0, returned=0, truncated=False, results=[])`
  Not an error — let Claude decide what to do.
- Empty identifier → `ToolError("identifier must not be empty.")`

---

## Special handling

- **Case-insensitive exact match** via toLower() on both sides.
  No fulltext index — scans Gene label. Fast enough for ~30k genes.
- **Flat list** sorted by organism_strain, locus_tag. No longer uses
  `_group_by_organism` helper (breaking change from v1 grouped dict).

---

## Changes from current

| Aspect | Current (v1) | New (v2) |
|---|---|---|
| Matching | Case-sensitive exact match | Case-insensitive via toLower() |
| Function | `def resolve_gene(ctx, identifier, organism)` | `async def` with Annotated params |
| Return | JSON string via `json.dumps` | `ResolveGeneResponse` Pydantic model |
| Errors | `return f"Error: {e}"` | `raise ToolError(str(e))` |
| Logging | `logger.info(...)` | `await ctx.info(...)` |
| Models | None | GeneMatch, ResolveGeneResponse |
| Limit | None | `limit` param with default 50 |
| Tags | None | `tags={"genes", "discovery"}` |

---

## Query Builder

**File:** `kg/queries_lib.py` — **case-insensitive matching.**

Change `build_resolve_gene` to use `toLower()` on both sides:

```cypher
WHERE (
    toLower(g.locus_tag) = toLower($identifier)
    OR toLower(g.gene_name) = toLower($identifier)
    OR ANY(id IN g.all_identifiers WHERE toLower(id) = toLower($identifier))
  )
  AND ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
```

Note: bypasses index on locus_tag property. Acceptable for this tool —
result set is small and query runs against the Gene label scan.

---

## API Function

**File:** `api/functions.py` — **add `limit` param.**

```python
def resolve_gene(
    identifier: str,
    organism: str | None = None,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
```

Changes:
- Add `limit: int | None = None` param
- Return `dict` with `{total_matching, results}` instead of raw `list[dict]`
- Run full query (no LIMIT in Cypher), count all results for
  `total_matching`, then slice by limit in Python. Same pattern as
  `list_organisms`.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
class GeneMatch(BaseModel):
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
    gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
    product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III, beta subunit')")
    organism_strain: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")

class ResolveGeneResponse(BaseModel):
    total_matching: int = Field(description="Total genes matching identifier + organism filter (e.g. 3)")
    returned: int = Field(description="Genes in this response (e.g. 3)")
    truncated: bool = Field(description="True if total_matching > returned")
    results: list[GeneMatch] = Field(description="Matching genes sorted by organism_strain, locus_tag")
```

- Define models inside `register_tools()`
- `async def` with `await ctx.info()` / `ToolError`
- `Annotated[type, Field(description=...)]` for all params
- Returns `ResolveGeneResponse` (not JSON string)
- No longer uses `_group_by_organism` — flat list from API

---

## About Content

About content is auto-generated from Pydantic models + human-authored
input YAML. Served via MCP resource at `docs://tools/resolve_gene`.

### Input YAML

**File:** `multiomics_explorer/inputs/tools/resolve_gene.yaml`

Create with `uv run python scripts/build_about_content.py --skeleton resolve_gene`,
then fill in:

```yaml
examples:
  - title: Resolve by locus_tag
    call: resolve_gene(identifier="PMM0001")
    response: |
      {"total_matching": 1, "returned": 1, "truncated": false,
       "results": [{"locus_tag": "PMM0001", "gene_name": "dnaN",
       "product": "DNA polymerase III, beta subunit",
       "organism_strain": "Prochlorococcus MED4"}]}

  - title: Resolve gene name across organisms
    call: resolve_gene(identifier="dnaN")
    response: |
      {"total_matching": 15, "returned": 15, "truncated": false,
       "results": [{"locus_tag": "PMM0001", ...}, ...]}

  - title: Scoped to one organism
    call: resolve_gene(identifier="dnaN", organism="MED4")

  - title: Chain to gene overview
    steps: |
      Step 1: resolve_gene(identifier="psbA")
              → collect locus_tags from results

      Step 2: gene_overview(gene_ids=["PMM1070", "PMT9312_1073", ...])
              → compare function across organisms

chaining:
  - "resolve_gene → gene_overview → get_homologs"
  - "resolve_gene → get_gene_details"
  - "resolve_gene → gene_ontology_terms"

mistakes:
  - "Case-insensitive: 'pmm0001' and 'PMM0001' both work"
  - wrong: "search_genes(search_text='PMM0001')  # wrong tool for ID lookup"
    right: "resolve_gene(identifier='PMM0001')  # exact identity resolution"
```

### Build

```bash
uv run python scripts/build_about_content.py resolve_gene
```

**Output:** `multiomics_explorer/skills/multiomics-kg-guide/references/tools/resolve_gene.md`

### Verify

```bash
pytest tests/unit/test_about_content.py -v          # consistency with tool schema
pytest tests/integration/test_about_examples.py -v  # examples execute against KG
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildResolveGene:
    test_identifier_uses_tolower               (new — verify toLower on all 3 match conditions)
    test_organism_filter_unchanged             (existing — organism filter already case-insensitive)
    test_no_organism_filter                    (existing)
    test_returns_expected_columns              (existing — locus_tag, gene_name, product, organism_strain)
    test_order_by                              (existing)
```

### Unit: API function (`test_api_functions.py`)

```
class TestResolveGene:
    test_returns_dict_with_total_and_results   (new — dict envelope instead of list)
    test_limit_slices_results                  (new)
    test_total_matching_reflects_full_count    (new — total_matching before limit)
    test_empty_results                         (update — now returns dict)
    test_empty_identifier_raises               (existing)
    test_whitespace_identifier_raises          (existing)
    test_organism_filter_passed                (existing)
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestResolveGeneWrapper:
    test_single_match_returns_response         (rewrite — Pydantic model, flat list)
    test_not_found_empty_results               (rewrite — ResolveGeneResponse with results=[])
    test_multi_match_flat_list                 (rewrite — no longer grouped dict)
    test_organism_filter_forwarded             (rewrite — async, Pydantic)
    test_truncation_metadata                   (new — limit triggers truncated=True)
    test_empty_identifier_raises_tool_error    (rewrite — ToolError not error string)
    test_generic_error_raises_tool_error       (rewrite — ToolError not error string)

Update EXPECTED_TOOLS — no change (resolve_gene already present).
```

### Unit: tool correctness (`test_tool_correctness.py`)

```
class TestResolveGeneCorrectness:
    (update all tests — Pydantic model response, flat list, attribute access)
```

### Integration (`test_mcp_tools.py`)

Against live KG:
- Known locus_tag returns match
- Gene name returns multiple organisms
- Case-insensitive matching works (e.g. "pmm0001")
- Organism filter narrows results

### Regression (`test_regression.py`)

Already in `TOOL_BUILDERS` — no change needed.

### Eval cases (`cases.yaml`)

```yaml
- id: resolve_gene_locus_tag
  tool: resolve_gene
  desc: Resolve by locus_tag returns exact match
  params:
    identifier: PMM0001
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain]

- id: resolve_gene_case_insensitive
  tool: resolve_gene
  desc: Case-insensitive matching works
  params:
    identifier: pmm0001
  expect:
    min_rows: 1
```

---

## Implementation Order

| Step | Layer | File(s) | What |
|---|---|---|---|
| 1 | L1 | `kg/queries_lib.py` | Case-insensitive matching with toLower() |
| 2 | L2 | `api/functions.py` | Add limit, return dict envelope |
| 3 | L3 | `mcp_server/tools.py` | v2 rewrite with Pydantic |
| 4 | L4 | `inputs/tools/resolve_gene.yaml` | About content input YAML + build |
| 5 | Tests | `tests/unit/test_query_builders.py` | Update Cypher assertions for toLower |
| 6 | Tests | `tests/unit/test_api_functions.py` | Update for dict return + limit |
| 7 | Tests | `tests/unit/test_tool_wrappers.py` | Rewrite for v2 pattern |
| 8 | Tests | `tests/unit/test_tool_correctness.py` | Update response shape |
| 9 | Tests | `tests/integration/test_mcp_tools.py` | Update integration tests |
| 10 | Tests | `tests/evals/cases.yaml` | Add case-insensitive eval case |
| 11 | Docs | `CLAUDE.md` | Update tool table row |

Steps 1-3 sequential, 4-11 after step 3.

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Update `resolve_gene` row — add "case-insensitive" to description |
