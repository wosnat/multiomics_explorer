# Tool spec: search_homolog_groups

## Purpose

Text search across OrthologGroup nodes via Lucene fulltext index.
Returns matching group IDs with metadata. Entry point for
cluster-centric discovery — feeds into `genes_by_homolog_group`.

Mirrors `search_ontology` in the ontology triplet.

## Out of scope

- **Member gene lists** — use `genes_by_homolog_group`
- **Gene → groups** — use `gene_homologs`
- **Expression data** — use `differential_expression_by_ortholog`
- **Group ID lookup** — this is text search, not ID resolution

## Status / Prerequisites

- [x] KG spec complete: `docs/kg-specs/kg-spec-search-homolog-groups.md`
- [x] KG changes landed (description, functional_description, edges, fulltext index)
- [x] Scope reviewed with user
- [x] Result-size controls decided (summary + limit)
- [x] Cypher drafted and verified against live KG
- [ ] Ready for Phase 2 (build) — awaiting approval

## Use cases

- **Cluster-centric discovery** — "What ortholog groups relate to
  photosynthesis?" → get group IDs for downstream use
- **Functional exploration** — browse OG landscape by function,
  filter by source/specificity
- **Chain:** `search_homolog_groups` → `genes_by_homolog_group` →
  `differential_expression_by_ortholog`

## KG dependencies

- `OrthologGroup` nodes: `id`, `name`, `source`, `taxonomic_level`,
  `specificity_rank`, `consensus_gene_name`, `consensus_product`,
  `description`, `functional_description`, `member_count`,
  `organism_count`, `genera`, `has_cross_genus_members`
- Fulltext index: `orthologGroupFullText` on `consensus_product`,
  `consensus_gene_name`, `description`, `functional_description`
- KG spec: `docs/kg-specs/kg-spec-search-homolog-groups.md`

All properties and index verified present in live KG (2026-03-26).

---

## Tool Signature

```python
@mcp.tool(
    tags={"homology", "search"},
    annotations={"readOnlyHint": True},
)
async def search_homolog_groups(
    ctx: Context,
    search_text: Annotated[str, Field(
        description="Search query (Lucene syntax). Searches consensus_product, "
        "consensus_gene_name, description, functional_description.",
    )],
    source: Annotated[str | None, Field(
        description="Filter by OG source: 'cyanorak' or 'eggnog'.",
    )] = None,
    taxonomic_level: Annotated[str | None, Field(
        description="Filter by taxonomic level. "
        "E.g. 'curated', 'Prochloraceae', 'Bacteria'.",
    )] = None,
    max_specificity_rank: Annotated[int | None, Field(
        description="Cap group breadth. 0=curated only, 1=+family, "
        "2=+order, 3=+domain (all).",
        ge=0, le=3,
    )] = None,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include description, functional_description, genera, "
        "has_cross_genus_members in results.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> SearchHomologGroupsResponse:
    """Search ortholog groups by text (Lucene). Returns group IDs for
    use with genes_by_homolog_group.

    Searches across consensus_product, consensus_gene_name, description,
    and functional_description fields.
    """
```

**Return envelope:**

```python
{
    "total_entries": 21122,       # all OGs in KG
    "total_matching": 884,        # matching search + filters
    "by_source": [{"source": "eggnog", "count": 647}, ...],
    "by_level": [{"taxonomic_level": "curated", "count": 237}, ...],
    "score_max": 6.128,           # null when total_matching=0
    "score_median": 1.057,        # null when total_matching=0
    "returned": 5,
    "truncated": true,
    "results": [...]
}
```

**Per-result columns (compact):** group_id, group_name,
consensus_gene_name, consensus_product, source, taxonomic_level,
specificity_rank, member_count, organism_count, score

**Verbose adds:** description, functional_description, genera,
has_cross_genus_members

## Result-size controls

Frequently large (e.g. "transporter" → 651 hits, "photosynthesis"
→ 884). Rich summary fields guide whether/how to inspect rows.

### Summary fields

| Field | Type | Description |
|---|---|---|
| total_entries | int | All OrthologGroup nodes (21,122) |
| total_matching | int | Groups matching search + filters |
| by_source | list[dict] | `[{source, count}]` sorted by count desc |
| by_level | list[dict] | `[{taxonomic_level, count}]` sorted by count desc |
| score_max | float\|null | Highest Lucene score (null when 0 matches) |
| score_median | float\|null | Median Lucene score (null when 0 matches) |

### Detail mode

| Field | Type | Compact | Verbose |
|---|---|---|---|
| group_id | str | x | x |
| group_name | str | x | x |
| consensus_gene_name | str\|null | x | x |
| consensus_product | str | x | x |
| source | str | x | x |
| taxonomic_level | str | x | x |
| specificity_rank | int | x | x |
| member_count | int | x | x |
| organism_count | int | x | x |
| score | float | x | x |
| description | str\|null | | x |
| functional_description | str\|null | | x |
| genera | list[str] | | x |
| has_cross_genus_members | str | | x |

**Sort key:** score DESC, specificity_rank ASC, source ASC

**Default limit:** 5 (MCP), None (api/)

**No `not_found`** — search tool, not batch.

---

## Query Builder

**File:** `kg/queries_lib.py`

Reuses `_gene_homologs_og_where()` for shared filter logic (source,
taxonomic_level, max_specificity_rank).

### `build_search_homolog_groups`

```python
def build_search_homolog_groups(
    *, search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for search_homolog_groups.

    RETURN keys (compact): group_id, group_name, consensus_gene_name,
    consensus_product, source, taxonomic_level, specificity_rank,
    member_count, organism_count, score.
    RETURN keys (verbose): adds description, functional_description,
    genera, has_cross_genus_members.
    """
```

**Verified Cypher (884 results for "photosynthesis"):**

```cypher
CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)
YIELD node AS og, score
-- WHERE og.source = $source AND og.taxonomic_level = $level
--   AND og.specificity_rank <= $max_rank (appended dynamically)
RETURN og.id AS group_id, og.name AS group_name,
       og.consensus_gene_name AS consensus_gene_name,
       og.consensus_product AS consensus_product,
       og.source AS source, og.taxonomic_level AS taxonomic_level,
       og.specificity_rank AS specificity_rank,
       og.member_count AS member_count, og.organism_count AS organism_count,
       score
       -- verbose adds:
       -- og.description AS description,
       -- og.functional_description AS functional_description,
       -- og.genera AS genera,
       -- og.has_cross_genus_members AS has_cross_genus_members
ORDER BY score DESC, og.specificity_rank, og.source
LIMIT $limit  -- when limit is not None
```

### `build_search_homolog_groups_summary`

```python
def build_search_homolog_groups_summary(
    *, search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for search_homolog_groups.

    RETURN keys: total_entries, total_matching, score_max, score_median,
    by_source, by_level.
    """
```

**Verified Cypher (total_matching matches detail count):**

```cypher
CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)
YIELD node AS og, score
-- WHERE filters appended dynamically
WITH collect(og.source) AS sources,
     collect(og.taxonomic_level) AS levels,
     count(og) AS total_matching,
     max(score) AS score_max,
     percentileDisc(score, 0.5) AS score_median
CALL { MATCH (all_og:OrthologGroup) RETURN count(all_og) AS total_entries }
RETURN total_entries, total_matching, score_max, score_median,
       apoc.coll.frequencies(sources) AS by_source,
       apoc.coll.frequencies(levels) AS by_level
```

**WHERE clause construction:** Shared with detail builder. Uses
`_gene_homologs_og_where()` which returns `(conditions, params)`.
Conditions joined with AND, prefixed with WHERE.

**Verified against live KG (2026-03-26):**
- "photosynthesis" no filter: 884 matches, summary == detail count ✓
- "photosynthesis" source=cyanorak: 237 matches ✓
- "transporter" taxonomic_level=curated: 123 matches ✓
- "kinase" source=cyanorak max_rank=0: 61 matches ✓
- Empty search ("xyznonexistent999"): 0 matches, score_max=null ✓
- Lucene special chars: hyphen needs space separation ✓

---

## API Function

**File:** `api/functions.py`

```python
def search_homolog_groups(
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Search ortholog groups by text (Lucene fulltext).

    Returns dict with keys: total_entries, total_matching, by_source,
    by_level, score_max, score_median, returned, truncated, results.
    Per result (compact): group_id, group_name, consensus_gene_name,
    consensus_product, source, taxonomic_level, specificity_rank,
    member_count, organism_count, score.
    Per result (verbose): adds description, functional_description,
    genera, has_cross_genus_members.

    summary=True: results=[], summary fields only.
    """
```

**Notes:**
- 2-query pattern: summary always runs, detail skipped when limit=0
- Lucene retry on `ClientError` (same pattern as `search_ontology`)
- Validates source, taxonomic_level, max_specificity_rank against constants
- `_apoc_freq_to_dict` to reshape by_source/by_level from apoc format
- Handles null score_max/score_median (0 matches)

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

**Pydantic models:**

```python
class SearchHomologGroupsResult(BaseModel):
    group_id: str = Field(description="OG identifier (e.g. 'cyanorak:CK_00000570')")
    group_name: str = Field(description="Raw OG name (e.g. 'CK_00000570')")
    consensus_gene_name: str | None = Field(default=None,
        description="Consensus gene name (e.g. 'psbB'). Often null.")
    consensus_product: str = Field(
        description="Consensus product (e.g. 'photosystem II chlorophyll-binding protein CP47')")
    source: str = Field(description="Source database (e.g. 'cyanorak')")
    taxonomic_level: str = Field(description="Taxonomic scope (e.g. 'curated')")
    specificity_rank: int = Field(description="0=curated, 1=family, 2=order, 3=domain")
    member_count: int = Field(description="Total genes in group (e.g. 9)")
    organism_count: int = Field(description="Distinct organisms (e.g. 9)")
    score: float = Field(description="Lucene relevance score")
    # verbose-only
    description: str | None = Field(default=None,
        description="Functional narrative from eggNOG (e.g. 'photosynthesis')")
    functional_description: str | None = Field(default=None,
        description="Derived from member gene roles (e.g. 'Photosynthesis and respiration > Photosystem II')")
    genera: list[str] | None = Field(default=None,
        description="Genera represented (e.g. ['Prochlorococcus', 'Synechococcus'])")
    has_cross_genus_members: str | None = Field(default=None,
        description="'cross_genus' or 'single_genus'")

class SearchHomologGroupsSourceBreakdown(BaseModel):
    source: str = Field(description="OG source (e.g. 'cyanorak')")
    count: int = Field(description="Groups from this source")

class SearchHomologGroupsLevelBreakdown(BaseModel):
    taxonomic_level: str = Field(description="Taxonomic level (e.g. 'curated')")
    count: int = Field(description="Groups at this level")

class SearchHomologGroupsResponse(BaseModel):
    total_entries: int = Field(description="Total OrthologGroup nodes in KG")
    total_matching: int = Field(description="Groups matching search + filters")
    by_source: list[SearchHomologGroupsSourceBreakdown] = Field(
        description="Groups per source, sorted by count desc")
    by_level: list[SearchHomologGroupsLevelBreakdown] = Field(
        description="Groups per taxonomic level, sorted by count desc")
    score_max: float | None = Field(description="Highest Lucene score (null if 0 matches)")
    score_median: float | None = Field(description="Median Lucene score (null if 0 matches)")
    returned: int = Field(description="Results in this response")
    truncated: bool = Field(description="True if total_matching > returned")
    results: list[SearchHomologGroupsResult] = Field(default_factory=list)
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildSearchHomologGroups:
    test_no_filters
    test_source_filter
    test_taxonomic_level_filter
    test_max_specificity_rank_filter
    test_combined_filters
    test_returns_expected_columns
    test_verbose_columns
    test_order_by
    test_limit_clause
    test_limit_none

class TestBuildSearchHomologGroupsSummary:
    test_no_filters
    test_with_filters
    test_shares_where_clause
```

### Unit: API function (`test_api_functions.py`)

```
class TestSearchHomologGroups:
    test_returns_dict
    test_passes_params
    test_summary_mode
    test_creates_conn_when_none
    test_validates_source
    test_validates_taxonomic_level
    test_lucene_retry
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestSearchHomologGroupsWrapper:
    test_returns_dict_envelope
    test_empty_results
    test_params_forwarded
    test_truncation_metadata

Update EXPECTED_TOOLS to include "search_homolog_groups".
```

### Integration (`test_mcp_tools.py`)

Against live KG:
- "photosynthesis" → returns expected count (~884)
- With source=cyanorak → ~237
- Each result has expected fields
- Summary total_matching == detail count

---

## About Content

**Input YAML:** `multiomics_explorer/inputs/tools/search_homolog_groups.yaml`

**Examples:**
- Basic search: `search_homolog_groups(search_text="photosynthesis")`
- Filtered: `search_homolog_groups(search_text="kinase", source="cyanorak")`
- Chain: search → `genes_by_homolog_group`

**Chaining:**
- `search_homolog_groups` → `genes_by_homolog_group` → `differential_expression_by_ortholog`
- `gene_homologs` → inspect group → `search_homolog_groups` for similar

**Mistakes:**
- Searching by group ID (e.g. "COG0592") — group IDs are not in the fulltext index
- Using hyphens in search — Lucene treats them as operators, use spaces instead

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add row to MCP Tools table |
