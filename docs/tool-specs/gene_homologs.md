# Tool spec: gene_homologs

## Purpose

Given gene locus tags, return which ortholog groups each gene belongs to.
Details tool in the homology triplet (`search_homolog_groups` →
`genes_by_homolog_group` → `gene_homologs`). Flat long format — one row
per gene × ortholog group.

Replaces `get_homologs` (v1), which had a nested group-centric shape
with optional member expansion.

## Out of Scope

- **Member gene lists** — use `genes_by_homolog_group` (E1)
- **Paralog filtering** — moved to `genes_by_homolog_group`
- **Expression data** — use `differential_expression_by_ortholog` (E2)
- **OrthologGroup text search** — use `search_homolog_groups` (E1)

## Status / Prerequisites

- [x] KG spec: not needed — all OrthologGroup properties exist
- [x] Scope reviewed with user
- [x] Result-size controls decided (summary + limit)
- [ ] Ready for Phase 2 (build)

## Use cases

- **Gene characterization** — "What ortholog groups does PMM0001 belong to?"
- **Batch annotation** — given 50 genes from a DE experiment, annotate
  each with its homology groups in one call
- **Cross-organism bridging** — identify which groups span multiple genera
- **Chain:** `resolve_gene` → `gene_homologs` → `genes_by_homolog_group`

## KG dependencies

- `Gene` nodes: `locus_tag`, `organism_strain`
- `OrthologGroup` nodes: `name`, `source`, `taxonomic_level`,
  `specificity_rank`, `consensus_gene_name`, `consensus_product`,
  `member_count`, `organism_count`, `genera`, `has_cross_genus_members`
- `Gene_in_ortholog_group` edges

All properties verified present in live KG (2026-03-23).

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes", "homology"},
    annotations={"readOnlyHint": True},
)
async def gene_homologs(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845'].",
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
        description="Include group metadata: specificity_rank, member_count, "
        "organism_count, genera, has_cross_genus_members.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GeneHomologsResponse:
    """Get ortholog group memberships for genes.

    Returns which ortholog groups each gene belongs to, ordered from most
    specific (curated) to broadest. Use for gene characterization and
    cross-organism bridging. A gene typically belongs to 1-3 groups.

    For member genes within a group, use genes_by_homolog_group.
    For text search on group names, use search_homolog_groups.
    """
```

**Return envelope:** `total_matching, by_organism, by_source, returned, truncated, not_found, no_groups, results`

**Per-result columns (compact — 7):**
`locus_tag`, `organism_strain`, `group_id`, `consensus_gene_name`,
`consensus_product`, `taxonomic_level`, `source`

**Verbose adds (5):**
`specificity_rank`, `member_count`, `organism_count`, `genera`,
`has_cross_genus_members`

## Result-size controls

Batch input can be large → summary + limit pattern.

### Summary fields (always present)

| Field | Type | Description |
|---|---|---|
| `total_matching` | int | Total gene×group rows matching filters |
| `by_organism` | list | Gene×group counts per organism, sorted desc |
| `by_source` | list | Gene×group counts per source (cyanorak/eggnog) |

### Batch handling

| Field | Type | Description |
|---|---|---|
| `not_found` | list[str] | Input locus_tags that don't exist in KG |
| `no_groups` | list[str] | Genes that exist but have zero matching OGs |

`no_groups` distinguishes "bad ID" from "gene exists but has no homology
data" — important because some genes genuinely have no ortholog group
membership.

**Sort key:** `locus_tag ASC, specificity_rank ASC, source ASC`

**Default limit:** 5 (MCP), None (api/)

**Verbose:**
- Compact: locus_tag, organism_strain, group_id, consensus_gene_name,
  consensus_product, taxonomic_level, source
- Verbose adds: specificity_rank, member_count, organism_count, genera,
  has_cross_genus_members

## Special handling

- **2-query pattern:** summary query always runs (OPTIONAL MATCH for
  not_found/no_groups), detail query skipped when `limit=0`
- **No Lucene:** no fulltext search
- **No caching:** result depends on input locus_tags
- **Validation:** source, taxonomic_level, max_specificity_rank validated
  against `kg/constants.py`

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_gene_homologs_summary`

```python
def build_gene_homologs_summary(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
) -> tuple[str, dict]:
    """Build summary + not_found/no_groups for gene_homologs.

    RETURN keys: total_matching, by_organism, by_source, not_found, no_groups.
    """
```

Cypher uses two OPTIONAL MATCHes:
1. `OPTIONAL MATCH (g:Gene {locus_tag: lt})` — gene existence
2. `OPTIONAL MATCH (g)-[:Gene_in_ortholog_group]->(og) WHERE [filters]` — OG membership

Classifies each input tag as not_found, no_groups, or has_results.
Uses `apoc.coll.frequencies` for by_organism and by_source breakdowns.

### `build_gene_homologs`

```python
def build_gene_homologs(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_homologs.

    RETURN keys (compact): locus_tag, organism_strain, group_id,
    consensus_gene_name, consensus_product, taxonomic_level, source.
    RETURN keys (verbose): adds specificity_rank, member_count,
    organism_count, genera, has_cross_genus_members.
    """
```

Both builders share WHERE clause construction via shared helper.

---

## API Function

**File:** `api/functions.py`

```python
def gene_homologs(
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get ortholog group memberships for genes.

    Returns dict with keys: total_matching, by_organism, by_source,
    returned, truncated, not_found, no_groups, results.
    """
```

- `summary=True` → `limit=0`
- Validate source, taxonomic_level, max_specificity_rank against constants
- Always run summary query → total_matching, breakdowns, not_found, no_groups
- Skip detail when `limit=0`
- Rename APOC `{item, count}` to domain keys, sort desc

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

Pydantic response models: `GeneHomologResult`, `GeneHomologsResponse`,
`HomologOrganismBreakdown`, `HomologSourceBreakdown`.

Thin wrapper: `Response(**data)` with standard error handling
(ValueError → ToolError, Exception → ToolError with prefix).

---

## Tests

| Layer | File | Test class |
|---|---|---|
| Query builder | `test_query_builders.py` | `TestBuildGeneHomologs`, `TestBuildGeneHomologsSummary` |
| API | `test_api_functions.py` | `TestGeneHomologs` |
| MCP wrapper | `test_tool_wrappers.py` | `TestGeneHomologsWrapper` + update EXPECTED_TOOLS |
| Integration | `test_mcp_tools.py` | Update existing homolog tests |
| Contract | `test_api_contract.py` | Update |
| Regression | `test_regression.py` | Update TOOL_BUILDERS |
| Evals | `cases.yaml` | Rename + update shape |

Remove old: `TestBuildGetHomologsGroups`, `TestBuildGetHomologsMembers`,
`TestGetHomologs`, `TestGetHomologsWrapper`, old eval cases.

---

## About Content

- Create `inputs/tools/gene_homologs.yaml`
- Run `build_about_content.py gene_homologs`
- Verify: `test_about_content.py` + `test_about_examples.py`

---

## Documentation

- `CLAUDE.md`: update tool table (rename + new description)
- Mark `plans/redefine_mcp_tools/get_homologs_redefinition.md` as superseded

## Code Review

Run code-review skill (full checklist) as final step.
