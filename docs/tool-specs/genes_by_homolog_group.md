# Tool spec: genes_by_homolog_group

## Purpose

Given ortholog group IDs, return member genes per organism. Discovery
tool in the homology triplet: `search_homolog_groups` →
**`genes_by_homolog_group`** → `gene_homologs`.

Mirrors `genes_by_ontology` in the ontology triplet.

## Out of Scope

- **Group text search** — use `search_homolog_groups` to find group IDs first
- **Gene → groups** — use `gene_homologs` (reverse direction)
- **Expression data** — use `differential_expression_by_ortholog`
- **Group metadata only** — use `search_homolog_groups` with the group name

## Status / Prerequisites

- [x] KG spec: not needed — existing `Gene_in_ortholog_group` edges suffice
- [x] Scope reviewed with user
- [x] Result-size controls decided (summary + verbose + limit)
- [x] Cypher drafted and verified against live KG
- [ ] Ready for Phase 2 (build) — awaiting approval

## Use cases

- **Ortholog group inspection** — "Which genes are in CK_00000570?"
  → see members per organism with gene annotations
- **Cross-organism comparison** — given a group ID from
  `search_homolog_groups`, see which organisms have members
- **Batch group lookup** — pass multiple group IDs, use `by_group`
  summary to compare member counts
- **Chain:** `search_homolog_groups` → `genes_by_homolog_group` →
  `differential_expression_by_gene`

## KG dependencies

- `Gene` nodes: `locus_tag`, `gene_name`, `product`,
  `organism_strain`, `gene_category`, `gene_summary`,
  `function_description`
- `OrthologGroup` nodes: `id`, `name`, `source`, `taxonomic_level`,
  `specificity_rank`, `consensus_gene_name`, `consensus_product`,
  `member_count`, `organism_count`, `description`,
  `functional_description`, `genera`, `has_cross_genus_members`
- `Gene_in_ortholog_group` edges (Gene → OrthologGroup)

All properties verified present in live KG (2026-03-26).

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes", "homology"},
    annotations={"readOnlyHint": True},
)
async def genes_by_homolog_group(
    ctx: Context,
    group_ids: Annotated[list[str], Field(
        description="Ortholog group IDs (from search_homolog_groups or gene_homologs). "
        "E.g. ['cyanorak:CK_00000570', 'eggnog:COG0592@2'].",
    )],
    organism: Annotated[str | None, Field(
        description="Filter by organism (case-insensitive substring). "
        "E.g. 'MED4', 'Alteromonas'. "
        "Use list_organisms to see valid values.",
    )] = None,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include gene_summary, function_description, and "
        "group context (consensus_product, source, taxonomic_level).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GenesByHomologGroupResponse:
    """Find member genes of ortholog groups.

    Takes group IDs from search_homolog_groups or gene_homologs and
    returns member genes per organism. One row per gene × group (a gene
    in multiple input groups appears once per group).

    For group discovery by text, use search_homolog_groups first.
    For gene → group direction, use gene_homologs.
    """
```

**Return envelope:**

```python
{
    "total_matching": 33,         # gene×group rows matching filters
    "total_genes": 30,            # distinct genes (a gene in 2 groups counted once)
    "by_organism": [{"organism": "Prochlorococcus MED4", "count": 2}, ...],
    "by_category": [{"category": "Photosynthesis", "count": 9}, ...],
    "by_group": [{"group_id": "eggnog:COG0592@2", "count": 13}, ...],
    "not_found": [],              # input group_ids not in KG
    "returned": 5,
    "truncated": true,
    "results": [...]
}
```

**Per-result columns (compact — 5):**
`locus_tag`, `gene_name`, `product`, `organism_strain`, `gene_category`

**Verbose adds (5):**
`gene_summary`, `function_description`, `group_id`, `consensus_product`,
`source`

**Design note — `group_id` in results:** In compact mode, all results
for a single `group_ids` call share the same group context. When
multiple group IDs are passed, `group_id` moves to compact mode to
disambiguate. However, the common case is single-group lookup, so
keeping `group_id` in verbose avoids redundancy. The `by_group`
summary always shows per-group counts regardless.

**Revised:** `group_id` is always in compact results — it's the
entity × dimension key (gene × group). Without it, rows from
multi-group queries are ambiguous. This matches `genes_by_ontology`
where `matched_terms` tracks the term dimension.

**Per-result columns (compact — 6):**
`locus_tag`, `gene_name`, `product`, `organism_strain`,
`gene_category`, `group_id`

**Verbose adds (4):**
`gene_summary`, `function_description`, `consensus_product`, `source`

## Result-size controls

Groups are typically small (median 3, p95 10, max 151 members), but
batch input of multiple group IDs can produce large results.

### Summary fields (always present)

| Field | Type | Description |
|---|---|---|
| `total_matching` | int | Gene×group rows matching all filters |
| `total_genes` | int | Distinct genes (a gene in 2 input groups counted once) |
| `by_organism` | list[dict] | `[{organism, count}]` sorted by count desc |
| `by_category` | list[dict] | `[{category, count}]` sorted by count desc |
| `by_group` | list[dict] | `[{group_id, count}]` sorted by count desc |

### Batch handling

| Field | Type | Description |
|---|---|---|
| `not_found` | list[str] | Input group_ids not in KG. Empty when all matched. |

No `no_members` field (unlike `gene_homologs`'s `no_groups`): an
OrthologGroup without members shouldn't exist in the KG. If it does,
it just returns 0 rows for that group — `by_group` won't list it,
and the user can infer from comparing input vs `by_group`.

### Detail mode

| Field | Type | Compact | Verbose |
|---|---|---|---|
| locus_tag | str | x | x |
| gene_name | str\|null | x | x |
| product | str\|null | x | x |
| organism_strain | str | x | x |
| gene_category | str\|null | x | x |
| group_id | str | x | x |
| gene_summary | str\|null | | x |
| function_description | str\|null | | x |
| consensus_product | str | | x |
| source | str | | x |

### Zero-match behavior

When `total_matching=0`: all summary fields present, counts are 0,
`total_genes=0`, breakdowns are empty lists, `results=[]`,
`returned=0`, `truncated=False`. `not_found` lists all input group_ids.

**Sort key:** `group_id ASC, organism_strain ASC, locus_tag ASC`

**Default limit:** 5 (MCP), None (api/)

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_genes_by_homolog_group_summary`

```python
def build_genes_by_homolog_group_summary(
    *,
    group_ids: list[str],
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_homolog_group.

    RETURN keys: total_matching, total_genes, by_organism, by_category,
    by_group, not_found.
    """
```

**Verified Cypher:**

```cypher
UNWIND $group_ids AS gid
OPTIONAL MATCH (og:OrthologGroup {id: gid})
OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og)
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
WITH gid, og, g
WITH collect(DISTINCT CASE WHEN og IS NULL THEN gid END) AS not_found_raw,
     collect(CASE WHEN g IS NOT NULL THEN
       {lt: g.locus_tag, org: g.organism_strain,
        cat: coalesce(g.gene_category, 'Unknown'), gid: gid} END) AS rows
WITH [x IN not_found_raw WHERE x IS NOT NULL] AS not_found, rows
WITH not_found,
     size(rows) AS total_matching,
     size(apoc.coll.toSet([r IN rows | r.lt])) AS total_genes,
     apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,
     apoc.coll.frequencies([r IN rows | r.cat]) AS by_category,
     apoc.coll.frequencies([r IN rows | r.gid]) AS by_group
RETURN total_matching, total_genes, not_found, by_organism, by_category, by_group
```

**Verified against live KG (2026-03-26):**
- 3 group_ids → total_matching=33, by_group counts match detail ✓
- With organism="MED4" → total_matching=2 ✓
- With 1 fake group_id → not_found=['FAKE_GROUP_999'] ✓
- All fake group_ids → total_matching=0, not_found=[all] ✓

### `build_genes_by_homolog_group`

```python
def build_genes_by_homolog_group(
    *,
    group_ids: list[str],
    organism: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_homolog_group.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_strain, gene_category, group_id.
    RETURN keys (verbose): adds gene_summary, function_description,
    consensus_product, source.
    """
```

**Verified Cypher (compact):**

```cypher
UNWIND $group_ids AS gid
MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain,
       g.gene_category AS gene_category, og.id AS group_id
ORDER BY og.id, g.organism_strain, g.locus_tag
LIMIT $limit  -- when limit is not None
```

**Verbose adds:**

```cypher
       , g.gene_summary AS gene_summary,
       g.function_description AS function_description,
       og.consensus_product AS consensus_product,
       og.source AS source
```

**Design notes:**
- No shared WHERE helper needed (unlike `gene_homologs` which filters
  on OG properties). This tool filters on organism only — the
  `group_ids` are exact-match via `{id: gid}`.
- `UNWIND $group_ids AS gid` + `MATCH ... {id: gid}` handles batch
  naturally — Neo4j uses the index on `OrthologGroup.id`.
- Detail query only returns matched groups (MATCH, not OPTIONAL MATCH)
  — `not_found` comes from the summary query.

---

## API Function

**File:** `api/functions.py`

```python
def genes_by_homolog_group(
    group_ids: list[str],
    organism: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Find member genes of ortholog groups.

    Returns dict with keys: total_matching, total_genes, by_organism,
    by_category, by_group, not_found, returned, truncated, results.
    Per result (compact): locus_tag, gene_name, product,
    organism_strain, gene_category, group_id.
    Per result (verbose): adds gene_summary, function_description,
    consensus_product, source.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if group_ids is empty.
    """
```

**Notes:**
- 2-query pattern: summary always runs, detail skipped when `limit=0`
- No Lucene search, no retry logic needed
- Validates `group_ids` non-empty (raises `ValueError`)
- `_apoc_freq_to_dict` to reshape by_organism/by_category/by_group
  from apoc `{item, count}` format to domain keys
- Organism filter passed to both summary and detail builders

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

**Pydantic models:**

```python
class GenesByHomologGroupResult(BaseModel):
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0315')")
    gene_name: str | None = Field(default=None,
        description="Gene name (e.g. 'psbB')")
    product: str | None = Field(default=None,
        description="Gene product (e.g. 'photosystem II chlorophyll-binding protein CP47')")
    organism_strain: str = Field(
        description="Organism (e.g. 'Prochlorococcus MED4')")
    gene_category: str | None = Field(default=None,
        description="Functional category (e.g. 'Photosynthesis')")
    group_id: str = Field(
        description="Ortholog group ID (e.g. 'cyanorak:CK_00000570')")
    # verbose only
    gene_summary: str | None = Field(default=None,
        description="Concatenated summary text")
    function_description: str | None = Field(default=None,
        description="Curated functional description")
    consensus_product: str | None = Field(default=None,
        description="Group consensus product (e.g. 'photosystem II chlorophyll-binding protein CP47')")
    source: str | None = Field(default=None,
        description="OG source (e.g. 'cyanorak')")

class HomologGroupOrganismBreakdown(BaseModel):
    organism: str = Field(
        description="Organism strain (e.g. 'Prochlorococcus MED4')")
    count: int = Field(description="Member genes from this organism")

class HomologGroupCategoryBreakdown(BaseModel):
    category: str = Field(
        description="Gene category (e.g. 'Photosynthesis')")
    count: int = Field(description="Member genes in this category")

class HomologGroupGroupBreakdown(BaseModel):
    group_id: str = Field(
        description="Ortholog group ID (e.g. 'cyanorak:CK_00000570')")
    count: int = Field(description="Member genes in this group")

class GenesByHomologGroupResponse(BaseModel):
    total_matching: int = Field(
        description="Gene×group rows matching filters (e.g. 33)")
    total_genes: int = Field(
        description="Distinct genes (a gene in 2 input groups counted once, e.g. 30)")
    by_organism: list[HomologGroupOrganismBreakdown] = Field(
        description="Member counts per organism, sorted by count desc")
    by_category: list[HomologGroupCategoryBreakdown] = Field(
        description="Member counts per gene category, sorted by count desc")
    by_group: list[HomologGroupGroupBreakdown] = Field(
        description="Member counts per input group, sorted by count desc")
    not_found: list[str] = Field(default_factory=list,
        description="Input group_ids not found in KG")
    returned: int = Field(description="Results in this response")
    truncated: bool = Field(
        description="True if total_matching > returned")
    results: list[GenesByHomologGroupResult] = Field(
        default_factory=list, description="One row per gene × group")
```

### Wrapper

```python
@mcp.tool(
    tags={"genes", "homology"},
    annotations={"readOnlyHint": True},
)
async def genes_by_homolog_group(
    ctx: Context,
    group_ids: Annotated[list[str], Field(
        description="Ortholog group IDs (from search_homolog_groups or "
        "gene_homologs). E.g. ['cyanorak:CK_00000570'].",
    )],
    organism: Annotated[str | None, Field(
        description="Filter by organism (case-insensitive substring). "
        "E.g. 'MED4', 'Alteromonas'. "
        "Use list_organisms to see valid values.",
    )] = None,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include gene_summary, function_description, "
        "consensus_product, source in results.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GenesByHomologGroupResponse:
    """Find member genes of ortholog groups.

    Takes group IDs from search_homolog_groups or gene_homologs and
    returns member genes per organism. One row per gene × group.

    For group discovery by text, use search_homolog_groups first.
    For gene → group direction, use gene_homologs.
    """
    await ctx.info(f"genes_by_homolog_group group_ids={group_ids} organism={organism}")
    try:
        conn = _conn(ctx)
        data = api.genes_by_homolog_group(
            group_ids, organism=organism,
            summary=summary, verbose=verbose, limit=limit, conn=conn,
        )
        by_organism = [HomologGroupOrganismBreakdown(**b) for b in data["by_organism"]]
        by_category = [HomologGroupCategoryBreakdown(**b) for b in data["by_category"]]
        by_group = [HomologGroupGroupBreakdown(**b) for b in data["by_group"]]
        results = [GenesByHomologGroupResult(**r) for r in data["results"]]
        return GenesByHomologGroupResponse(
            total_matching=data["total_matching"],
            total_genes=data["total_genes"],
            by_organism=by_organism,
            by_category=by_category,
            by_group=by_group,
            not_found=data["not_found"],
            returned=data["returned"],
            truncated=data["truncated"],
            results=results,
        )
    except ValueError as e:
        await ctx.warning(f"genes_by_homolog_group error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"genes_by_homolog_group unexpected error: {e}")
        raise ToolError(f"Error in genes_by_homolog_group: {e}")
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildGenesByHomologGroup:
    test_single_group_id
    test_multiple_group_ids
    test_organism_filter_clause
    test_returns_expected_columns
    test_verbose_columns
    test_order_by
    test_limit_clause
    test_limit_none

class TestBuildGenesByHomologGroupSummary:
    test_returns_summary_keys
    test_organism_filter
    test_not_found_detection
```

### Unit: API function (`test_api_functions.py`)

```
class TestGenesByHomologGroup:
    test_returns_dict
    test_passes_params (group_ids, organism, verbose, limit)
    test_summary_sets_limit_zero
    test_creates_conn_when_none
    test_empty_group_ids_raises
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestGenesByHomologGroupWrapper:
    test_returns_dict_envelope
    test_empty_results
    test_params_forwarded (group_ids, organism, summary, verbose, limit)
    test_truncation_metadata
    test_not_found

Update EXPECTED_TOOLS to include "genes_by_homolog_group".
```

### Integration (`test_tool_correctness_kg.py`)

Against live KG:
- Single group_id → expected member count
- Multiple group_ids → results from all groups
- Organism filter reduces results
- Not-found group_id → appears in not_found
- Each result has expected compact columns
- Summary total_matching == detail count

### Regression (`test_regression.py`)

Add to `TOOL_BUILDERS`:
```python
"genes_by_homolog_group": build_genes_by_homolog_group,
```

Add baseline fixtures:
- `genes_by_homolog_group_basic.yml` (single group)
- `genes_by_homolog_group_organism_filter.yml`
- `genes_by_homolog_group_verbose.yml`

### Eval cases (`cases.yaml`)

```yaml
- id: genes_by_homolog_group_basic
  tool: genes_by_homolog_group
  desc: Single group to member genes
  params:
    group_ids: ["cyanorak:CK_00000570"]
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain, group_id]

- id: genes_by_homolog_group_organism_filter
  tool: genes_by_homolog_group
  desc: Group members filtered by organism
  params:
    group_ids: ["cyanorak:CK_00000570"]
    organism: "MED4"
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain, group_id]

- id: genes_by_homolog_group_multi
  tool: genes_by_homolog_group
  desc: Multiple groups
  params:
    group_ids: ["cyanorak:CK_00000570", "eggnog:COG0592@2"]
  expect:
    min_rows: 2
    columns: [locus_tag, organism_strain, group_id]
```

---

## About Content

### Input YAML

**File:** `multiomics_explorer/inputs/tools/genes_by_homolog_group.yaml`

```yaml
examples:
  - title: Find members of an ortholog group
    call: genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"])
    response: |
      {
        "total_matching": 9,
        "by_organism": [{"organism": "Prochlorococcus MED4", "count": 1}, ...],
        "by_category": [{"category": "Photosynthesis", "count": 9}],
        "by_group": [{"group_id": "cyanorak:CK_00000570", "count": 9}],
        "not_found": [],
        "returned": 5, "truncated": true,
        "results": [
          {"locus_tag": "A9601_03391", "gene_name": "psbB",
           "product": "photosystem II chlorophyll-binding protein CP47",
           "organism_strain": "Prochlorococcus AS9601",
           "gene_category": "Photosynthesis",
           "group_id": "cyanorak:CK_00000570"},
          ...
        ]
      }

  - title: Filter to one organism
    call: genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"], organism="MED4")

  - title: From text search to member genes
    steps: |
      Step 1: search_homolog_groups(search_text="photosystem II")
              → collect group_ids from results (e.g. "cyanorak:CK_00000570")

      Step 2: genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"])
              → find member genes per organism

      Step 3: gene_overview(locus_tags=["PMM0315", ...])
              → check data availability for discovered genes

  - title: Compare membership across groups
    call: genes_by_homolog_group(group_ids=["cyanorak:CK_00000570", "eggnog:COG0592@2"], summary=true)
    response: |
      {
        "total_matching": 22,
        "by_group": [{"group_id": "eggnog:COG0592@2", "count": 13},
                     {"group_id": "cyanorak:CK_00000570", "count": 9}],
        "returned": 0, "truncated": true, "results": []
      }

verbose_fields:
  - gene_summary
  - function_description
  - consensus_product
  - source

chaining:
  - "search_homolog_groups → genes_by_homolog_group"
  - "genes_by_homolog_group → gene_overview"
  - "genes_by_homolog_group → differential_expression_by_gene"
  - "gene_homologs → genes_by_homolog_group"

mistakes:
  - "group_ids must be full IDs with prefix (e.g. 'cyanorak:CK_00000570', not 'CK_00000570')"
  - "A gene in multiple input groups appears once per group — rows are gene × group, not distinct genes"
  - wrong: "genes_by_homolog_group(group_ids=['photosystem'])  # passing text, not IDs"
    right: "search_homolog_groups(search_text='photosystem')  # search first, then use IDs"
```

### Build

```bash
uv run python scripts/build_about_content.py genes_by_homolog_group
```

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_genes_by_homolog_group()` + `build_genes_by_homolog_group_summary()` |
| 2 | API function | `api/functions.py` | `genes_by_homolog_group()` |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | Pydantic models + wrapper |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildGenesByHomologGroup` + `TestBuildGenesByHomologGroupSummary` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `TestGenesByHomologGroup` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestGenesByHomologGroupWrapper` + update EXPECTED_TOOLS |
| 8 | Unit tests | `tests/unit/test_tool_correctness.py` | Add expected keys |
| 9 | Regression | `tests/regression/test_regression.py` | Add to TOOL_BUILDERS + baselines |
| 10 | Eval cases | `tests/evals/cases.yaml` | Add cases |
| 11 | About content | `multiomics_explorer/inputs/tools/genes_by_homolog_group.yaml` | Input YAML → build |
| 12 | Docs | `CLAUDE.md` | Add row to MCP Tools table |
| 13 | Code review | — | Run code-review skill |

---

## Documentation

- `CLAUDE.md`: add `genes_by_homolog_group` row to MCP Tools table —
  "Group IDs → member genes per organism. Summary fields (by_organism,
  by_category, by_group). Filterable by organism."

## Code Review

Run code-review skill (full checklist) as final step.
