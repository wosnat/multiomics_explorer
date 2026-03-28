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
    organisms: Annotated[list[str] | None, Field(
        description="Filter by organisms (case-insensitive substring, each entry "
        "matched independently). E.g. ['MED4', 'AS9601']. "
        "Use list_organisms to see valid values.",
    )] = None,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include gene_summary, function_description, and "
        "group context (consensus_product, source).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GenesByHomologGroupResponse:
    """Find member genes of ortholog groups.

    Takes group IDs from search_homolog_groups or gene_homologs and
    returns member genes per organism. One row per gene × group (a gene
    in multiple input groups appears once per group).

    Two list filters — each reports not_found (doesn't exist in KG) +
    not_matched (exists, zero results after other filters):
    - group_ids: ortholog groups (required)
    - organisms: restrict to specific organisms

    For group discovery by text, use search_homolog_groups first.
    For gene → group direction, use gene_homologs.
    For expression by ortholog groups, use differential_expression_by_ortholog.
    """
```

**Return envelope:**

```python
{
    "total_matching": 33,         # gene×group rows matching filters
    "total_genes": 30,            # distinct genes (a gene in 2 groups counted once)
    "total_categories": 12,       # distinct gene categories
    "genes_per_group_max": 13,    # largest group's gene count
    "genes_per_group_median": 3.0,# median gene count across groups
    "by_organism": [{"organism": "Prochlorococcus MED4", "count": 2}, ...],
    "top_categories": [{"category": "Photosynthesis", "count": 9}, ...],  # top 5
    "top_groups": [{"group_id": "eggnog:COG0592@2", "count": 13}, ...],   # top 5
    "not_found_groups": [],       # group_ids with no OrthologGroup node
    "not_matched_groups": [],     # groups exist but 0 members after organism filter
    "not_found_organisms": [],    # organisms matching no Gene nodes in KG
    "not_matched_organisms": [],  # organisms exist but 0 genes in these groups
    "returned": 5,
    "truncated": true,
    "results": [...]
}
```

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
| `total_categories` | int | Distinct gene categories |
| `genes_per_group_max` | int | Largest group's gene count |
| `genes_per_group_median` | float | Median gene count across groups |
| `by_organism` | list[dict] | `[{organism, count}]` sorted by count desc (all) |
| `top_categories` | list[dict] | `[{category, count}]` sorted by count desc (top 5) |
| `top_groups` | list[dict] | `[{group_id, count}]` sorted by count desc (top 5) |

### Batch handling — per-filter not_found + not_matched

Each list filter gets **two** diagnostic lists:

- **not_found** — input value doesn't exist in the KG at all
- **not_matched** — exists in KG but contributed zero rows after other filters

| Field | Type | Description |
|---|---|---|
| `not_found_groups` | list[str] | Input `group_ids` with no OrthologGroup node in KG. |
| `not_matched_groups` | list[str] | Groups that exist but have zero member genes after organism filter. |
| `not_found_organisms` | list[str] | Input `organisms` entries matching zero Gene nodes in KG (bad name). |
| `not_matched_organisms` | list[str] | Organisms that exist in KG but have zero genes in the requested groups. |

**Semantics:**
- not_found is absolute — checked against KG independently of other
  filters. "This ID doesn't exist."
- not_matched is contextual — depends on the intersection of filters.
  "This exists, but nothing matched given the other inputs."
- An input appears in at most one of {not_found, not_matched} — never
  both (not_found takes precedence).
- When a filter is None, both its lists are empty `[]`.

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
`total_genes=0`, `total_categories=0`, `genes_per_group_max=0`,
`genes_per_group_median=0`, breakdowns are empty lists,
`results=[]`, `returned=0`, `truncated=False`. Each input value
appears in either its not_found or not_matched list.

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
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_homolog_group.

    RETURN keys: total_matching, total_genes, total_categories,
    genes_per_group_max, genes_per_group_median,
    by_organism, top_categories, top_groups,
    not_found_groups, not_matched_groups.
    """
```

**Cypher (sketch — needs live verification):**

```cypher
// Phase 1: find groups + member genes (with organism filter)
UNWIND $group_ids AS gid
OPTIONAL MATCH (og:OrthologGroup {id: gid})
OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og)
WHERE ($organisms IS NULL OR ANY(org_input IN $organisms
       WHERE ALL(word IN split(toLower(org_input), ' ')
             WHERE toLower(g.organism_strain) CONTAINS word)))
// Phase 2: collect not_found, not_matched, aggregates
WITH collect(DISTINCT CASE WHEN og IS NULL THEN gid END) AS nf_groups_raw,
     collect(DISTINCT CASE WHEN og IS NOT NULL AND g IS NULL THEN gid END) AS nm_groups_raw,
     collect(CASE WHEN g IS NOT NULL THEN
       {lt: g.locus_tag, org: g.organism_strain,
        cat: coalesce(g.gene_category, 'Unknown'), gid: gid} END) AS rows
WITH [x IN nf_groups_raw WHERE x IS NOT NULL] AS not_found_groups,
     [x IN nm_groups_raw WHERE x IS NOT NULL] AS not_matched_groups,
     rows
WITH not_found_groups, not_matched_groups,
     size(rows) AS total_matching,
     size(apoc.coll.toSet([r IN rows | r.lt])) AS total_genes,
     size(apoc.coll.toSet([r IN rows | r.cat])) AS total_categories,
     apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,
     apoc.coll.frequencies([r IN rows | r.cat]) AS by_category_raw,
     apoc.coll.frequencies([r IN rows | r.gid]) AS by_group_raw
RETURN total_matching, total_genes, total_categories,
       not_found_groups, not_matched_groups,
       by_organism, by_category_raw, by_group_raw
// API layer: sorts by count desc, caps top_categories/top_groups to 5,
// computes genes_per_group_max/median from by_group_raw counts
```

### `build_genes_by_homolog_group_diagnostics`

Separate lightweight query for organism not_found vs not_matched.

```python
def build_genes_by_homolog_group_diagnostics(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
    """Validate organisms against KG + result set.

    RETURN keys: not_found_organisms, not_matched_organisms.
    Returns empty lists when organisms is None.
    """
```

**Cypher (sketch):**

```cypher
WITH $organisms AS org_inputs
UNWIND CASE WHEN org_inputs IS NULL THEN [null]
       ELSE org_inputs END AS org_input
// Check existence in KG (any Gene node matching this organism)
OPTIONAL MATCH (g_any:Gene)
WHERE org_input IS NOT NULL
  AND ALL(word IN split(toLower(org_input), ' ')
          WHERE toLower(g_any.organism_strain) CONTAINS word)
WITH org_input, count(g_any) AS kg_count
// For those that exist, check if they match any group member
OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup)
WHERE org_input IS NOT NULL AND kg_count > 0
  AND og.id IN $group_ids
  AND ALL(word IN split(toLower(org_input), ' ')
          WHERE toLower(g.organism_strain) CONTAINS word)
WITH org_input, kg_count, count(g) AS matched_count
WITH collect(CASE WHEN org_input IS NOT NULL AND kg_count = 0
             THEN org_input END) AS nf_raw,
     collect(CASE WHEN org_input IS NOT NULL AND kg_count > 0
                   AND matched_count = 0 THEN org_input END) AS nm_raw
RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_organisms,
       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_organisms
```

### `build_genes_by_homolog_group`

```python
def build_genes_by_homolog_group(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
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

**Cypher (compact):**

```cypher
UNWIND $group_ids AS gid
MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})
WHERE ($organisms IS NULL OR ANY(org_input IN $organisms
       WHERE ALL(word IN split(toLower(org_input), ' ')
             WHERE toLower(g.organism_strain) CONTAINS word)))
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
- `organisms` list uses OR semantics: a gene matches if it belongs to
  ANY of the listed organisms. Cross-organism is the point.
- `UNWIND $group_ids AS gid` + `MATCH ... {id: gid}` handles batch
  naturally — Neo4j uses the index on `OrthologGroup.id`.
- Detail query only returns matched groups (MATCH, not OPTIONAL MATCH)
  — `not_found_groups` comes from the summary query.

---

## API Function

**File:** `api/functions.py`

```python
def genes_by_homolog_group(
    group_ids: list[str],
    organisms: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Find member genes of ortholog groups.

    Returns dict with keys: total_matching, total_genes,
    total_categories, genes_per_group_max, genes_per_group_median,
    by_organism, top_categories, top_groups,
    not_found_groups, not_matched_groups,
    not_found_organisms, not_matched_organisms,
    returned, truncated, results.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if group_ids is empty.
    """
```

**Notes:**
- 3-query pattern: summary + diagnostics + detail (skip when `limit=0`)
- Summary query: `not_found_groups`, `not_matched_groups`, all
  breakdowns. Returns `by_category_raw` and `by_group_raw` as full
  frequency lists; API layer sorts desc, caps to top 5 for
  `top_categories`/`top_groups`, and computes
  `genes_per_group_max`/`genes_per_group_median` from `by_group_raw`
  counts
- Diagnostics query: `not_found_organisms`, `not_matched_organisms`
  (skipped when `organisms is None`)
- Detail query: skipped when `limit=0`
- `_rename_freq` to reshape `{item, count}` → domain keys

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
        description="Gene product")
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
        description="Group consensus product")
    source: str | None = Field(default=None,
        description="OG source (e.g. 'cyanorak')")

class HomologGroupOrganismBreakdown(BaseModel):
    organism: str
    count: int

class HomologGroupCategoryBreakdown(BaseModel):
    category: str
    count: int

class HomologGroupGroupBreakdown(BaseModel):
    group_id: str
    count: int

class GenesByHomologGroupResponse(BaseModel):
    total_matching: int
    total_genes: int
    total_categories: int
    genes_per_group_max: int
    genes_per_group_median: float
    by_organism: list[HomologGroupOrganismBreakdown]
    top_categories: list[HomologGroupCategoryBreakdown]
    top_groups: list[HomologGroupGroupBreakdown]
    not_found_groups: list[str] = Field(default_factory=list)
    not_matched_groups: list[str] = Field(default_factory=list)
    not_found_organisms: list[str] = Field(default_factory=list)
    not_matched_organisms: list[str] = Field(default_factory=list)
    returned: int
    truncated: bool
    results: list[GenesByHomologGroupResult] = Field(default_factory=list)
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildGenesByHomologGroup:
    test_single_group_id
    test_multiple_group_ids
    test_organisms_filter_clause
    test_returns_expected_columns
    test_verbose_columns
    test_order_by
    test_limit_clause
    test_limit_none

class TestBuildGenesByHomologGroupSummary:
    test_returns_summary_keys  # total_matching, total_genes, total_categories, etc.
    test_organisms_filter
    test_not_found_groups_detection
    test_not_matched_groups_detection
    test_top_categories_and_top_groups_in_return

class TestBuildGenesByHomologGroupDiagnostics:
    test_organisms_none_returns_empty
    test_organisms_not_found_vs_not_matched
```

### Unit: API function (`test_api_functions.py`)

```
class TestGenesByHomologGroup:
    test_returns_dict
    test_passes_params (group_ids, organisms, verbose, limit)
    test_summary_sets_limit_zero
    test_creates_conn_when_none
    test_empty_group_ids_raises
    test_importable_from_package
    test_not_found_and_not_matched_fields
    test_top_categories_capped_at_5
    test_top_groups_capped_at_5
    test_genes_per_group_stats
    test_total_categories_count
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestGenesByHomologGroupWrapper:
    test_returns_dict_envelope
    test_empty_results
    test_params_forwarded (group_ids, organisms, summary, verbose, limit)
    test_truncation_metadata
    test_not_found_groups
    test_not_matched_groups
    test_not_found_organisms
    test_not_matched_organisms

Update EXPECTED_TOOLS to include "genes_by_homolog_group".
```

### Integration (`test_tool_correctness_kg.py`)

Against live KG:
- Single group_id → expected member count
- Multiple group_ids → results from all groups
- Organisms filter reduces results
- Fake group_id → appears in not_found_groups
- Real group with organism filter excluding all members → not_matched_groups
- Fake organism → appears in not_found_organisms
- Real organism not in these groups → not_matched_organisms
- Each result has expected compact columns
- Summary total_matching == detail count
- top_categories and top_groups capped at 5
- genes_per_group_max/median values are correct

### Integration (`test_api_contract.py`)

Update `TestGenesByHomologGroupContract` — return shape changed:
- New keys: `total_categories`, `genes_per_group_max`,
  `genes_per_group_median`
- Renamed keys: `by_category` → `top_categories`,
  `by_group` → `top_groups`

### Regression (`test_regression.py`)

Add to `TOOL_BUILDERS`:
```python
"genes_by_homolog_group": build_genes_by_homolog_group,
```

Add baseline fixtures:
- `genes_by_homolog_group_basic.yml` (single group)
- `genes_by_homolog_group_organism_filter.yml`
- `genes_by_homolog_group_verbose.yml`

### Eval (`test_eval.py`)

Add to `TOOL_BUILDERS`:
```python
"genes_by_homolog_group": build_genes_by_homolog_group,
```

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
  desc: Group members filtered by organisms
  params:
    group_ids: ["cyanorak:CK_00000570"]
    organisms: ["MED4"]
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

## Comparison: genes_by_homolog_group vs differential_expression_by_gene

### Inputs

| Parameter | genes_by_homolog_group | differential_expression_by_gene |
|---|---|---|
| Primary input | `group_ids: list[str]` (required) | At least one of organism/locus_tags/experiment_ids |
| Organism filter | `organisms: list[str]\|None` — multi-select, OR semantics, cross-organism OK | `organism: str\|None` — single fuzzy string, enforces single organism |
| Gene filter | — (genes come from group membership) | `locus_tags: list[str]\|None` — direct gene input |
| Experiment filter | — | `experiment_ids: list[str]\|None` |
| Expression filters | — | `direction: up\|down\|None`, `significant_only: bool` |
| summary/verbose/limit | Same pattern | Same pattern |

### Summary fields

| Field | genes_by_homolog_group | differential_expression_by_gene |
|---|---|---|
| Row count | `total_matching` (gene×group rows) | `total_rows` (gene×experiment×timepoint rows) |
| Gene count | `total_genes` (distinct genes) | `matching_genes` (distinct genes) |
| Category count | `total_categories` (distinct) | — |
| Group size stats | `genes_per_group_max`, `genes_per_group_median` | — |
| Organism breakdown | `by_organism` [{organism, count}] (all) | — (single organism) |
| Category breakdown | `top_categories` [{category, count}] (top 5) | `top_categories` (top 5) |
| Primary dimension | `top_groups` [{group_id, count}] (top 5) | `experiments` (nested per-experiment) |
| Expression signal | — | `rows_by_status` {sig_up, sig_down, not_sig} |
| not_found | `not_found_groups`, `not_found_organisms` | `not_found` (locus_tags only) |
| not_matched | `not_matched_groups`, `not_matched_organisms` | `no_expression` (genes with 0 edges) |

### Detail result columns

| Column | genes_by_homolog_group | differential_expression_by_gene |
|---|---|---|
| Gene identity | `locus_tag`, `gene_name` | `locus_tag`, `gene_name` |
| Gene annotation | `product`, `gene_category` | — (compact), `product`, `gene_category` (verbose) |
| Organism | `organism_strain` | — (single organism in header) |
| Primary dimension | `group_id` | `experiment_id`, `treatment_type` |
| Expression data | — | `timepoint`, `log2fc`, `padj`, `rank`, `expression_status` |
| Sort key | group_id ASC, organism ASC, locus_tag ASC | \|log2FC\| DESC |

---

## Comparison: homolog tool triplet

### Input parameters

| Parameter | search_homolog_groups | genes_by_homolog_group | gene_homologs |
|---|---|---|---|
| Primary input | `search_text: str` | `group_ids: list[str]` | `locus_tags: list[str]` |
| Direction | Text → groups | Groups → genes | Genes → groups |
| Organism filter | — | `organisms: list[str]\|None` | — |
| Source filter | `source: str\|None` | — | `source: str\|None` |
| Level filter | `taxonomic_level: str\|None` | — | `taxonomic_level: str\|None` |
| Rank filter | `max_specificity_rank: int\|None` | — | `max_specificity_rank: int\|None` |
| summary/verbose/limit | ✓ | ✓ | ✓ |

### Summary fields

| Field | search_homolog_groups | genes_by_homolog_group | gene_homologs |
|---|---|---|---|
| Row count | `total_matching` (groups) | `total_matching` (gene×group) | `total_matching` (gene×group) |
| Entity count | `total_entries` (all OGs) | `total_genes` (distinct genes) | — |
| Category count | — | `total_categories` (distinct) | — |
| Group size stats | — | `genes_per_group_max`, `genes_per_group_median` | — |
| by_organism | — | ✓ [{organism, count}] (all) | ✓ [{organism, count}] |
| top_categories | — | ✓ [{category, count}] (top 5) | — |
| top_groups | — | ✓ [{group_id, count}] (top 5) | — |
| by_source | ✓ [{source, count}] | — | ✓ [{source, count}] |
| by_level | ✓ [{taxonomic_level, count}] | — | — |
| Score stats | `score_max`, `score_median` | — | — |
| not_found | — | `not_found_{groups,organisms}` | `not_found` (locus_tags) |
| not_matched | — | `not_matched_{groups,organisms}` | `no_groups` (genes with 0 OGs) |

### Compact result columns

| Column | search_homolog_groups | genes_by_homolog_group | gene_homologs |
|---|---|---|---|
| Gene identity | — | `locus_tag`, `gene_name` | `locus_tag`, `organism_strain` |
| Gene annotation | — | `product`, `organism_strain`, `gene_category` | — |
| Group identity | `group_id`, `group_name` | `group_id` | `group_id` |
| Group annotation | `consensus_gene_name`, `consensus_product` | — | `consensus_gene_name`, `consensus_product` |
| Group metadata | `source`, `taxonomic_level`, `specificity_rank` | — | `taxonomic_level`, `source`, `specificity_rank` |
| Group size | `member_count`, `organism_count` | — | — |
| Search score | `score` | — | — |

### Chaining flow

```
search_homolog_groups(text)  →  group_ids
                                    ↓
                         genes_by_homolog_group(group_ids)  →  locus_tags
                                    ↓                              ↓
                    differential_expression_by_ortholog          gene_overview

gene_homologs(locus_tags)  →  group_ids  →  genes_by_homolog_group
```

---

## KG verification (2026-03-26)

Verified against live KG:
- Organism list filter (OR semantics): `["MED4", "AS9601"]` → 2 genes ✓
- not_found_groups: `["FAKE_GROUP"]` detected ✓
- not_found_organisms: `["NONEXISTENT_ORG"]` detected (gene_count=0) ✓
- by_expression for CK_00000570: 5 has_data, 4 no_data (9 total) ✓
- Full summary with organism filter + not_found_groups: works ✓

---

## About Content

Auto-generated from Pydantic models + input YAML. Served via MCP
resource at `docs://tools/genes_by_homolog_group`.

### Build

```bash
uv run python scripts/build_about_content.py genes_by_homolog_group
```

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

### Input YAML

**File:** `multiomics_explorer/inputs/tools/genes_by_homolog_group.yaml`

```yaml
examples:
  - title: Find members of an ortholog group
    call: genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"])
    response: |
      {
        "total_matching": 9, "total_genes": 9,
        "total_categories": 1,
        "genes_per_group_max": 9, "genes_per_group_median": 9.0,
        "by_organism": [{"organism": "Prochlorococcus MED4", "count": 1}, ...],
        "top_categories": [{"category": "Photosynthesis", "count": 9}],
        "top_groups": [{"group_id": "cyanorak:CK_00000570", "count": 9}],
        "not_found_groups": [], "not_matched_groups": [],
        "not_found_organisms": [], "not_matched_organisms": [],
        "returned": 5, "truncated": true,
        "results": [...]
      }

  - title: Filter to specific organisms
    call: genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"], organisms=["MED4", "AS9601"])

  - title: From text search to expression by ortholog
    steps: |
      Step 1: search_homolog_groups(search_text="photosystem II")
              → collect group_ids

      Step 2: genes_by_homolog_group(group_ids=[...])
              → see members per organism

      Step 3: differential_expression_by_ortholog(group_ids=[...], organisms=[...])
              → expression data framed by ortholog group

  - title: Compare membership across groups (summary only)
    call: genes_by_homolog_group(group_ids=["cyanorak:CK_00000570", "eggnog:COG0592@2"], summary=True)

verbose_fields:
  - gene_summary
  - function_description
  - consensus_product
  - source

chaining:
  - "search_homolog_groups → genes_by_homolog_group"
  - "genes_by_homolog_group → differential_expression_by_ortholog"
  - "genes_by_homolog_group → gene_overview"
  - "gene_homologs → genes_by_homolog_group"

mistakes:
  - "group_ids must be full IDs with prefix (e.g. 'cyanorak:CK_00000570', not 'CK_00000570')"
  - "A gene in multiple input groups appears once per group — rows are gene × group, not distinct genes. Use total_genes for deduplicated count."
  - "organisms is a list, not a string — use ['MED4'] not 'MED4'"
  - wrong: "genes_by_homolog_group(group_ids=['photosystem'])  # passing text, not IDs"
    right: "search_homolog_groups(search_text='photosystem')  # search first, then use IDs"
```

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_genes_by_homolog_group()` + `build_genes_by_homolog_group_summary()` + `build_genes_by_homolog_group_diagnostics()` |
| 2 | API function | `api/functions.py` | `genes_by_homolog_group()` |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | Pydantic models + wrapper |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | Query builder tests |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | API function tests |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | Wrapper tests + EXPECTED_TOOLS |
| 8 | Unit tests | `tests/unit/test_tool_correctness.py` | Expected keys |
| 9 | Integration | `tests/integration/test_api_contract.py` | Update return shape contract |
| 10 | Regression | `tests/regression/test_regression.py` | TOOL_BUILDERS + baselines |
| 11 | Eval | `tests/evals/test_eval.py` | TOOL_BUILDERS |
| 12 | Eval cases | `tests/evals/cases.yaml` | Add cases |
| 13 | About content | `inputs/tools/genes_by_homolog_group.yaml` | Input YAML → build + verify |
| 14 | Docs | `CLAUDE.md` | Update tools table |
| 15 | Code review | — | Run code-review skill |

---

## Documentation

- `CLAUDE.md`: update `genes_by_homolog_group` row —
  "Group IDs → member genes per organism. Summary fields (by_organism,
  top_categories, top_groups, total_categories,
  genes_per_group_max/median). Batch tool with not_found/not_matched
  for groups and organisms. Filterable by organism."
