# Tool spec: gene_overview

## Purpose

Batch gene routing: given locus tags, return identity + data availability
signals for each gene. Tells the LLM what each gene is and what follow-up
tools have data for it (expression, ontology, homology).

Details tool in Phase 2 Gene work. Not a rename — same name, v3 upgrade.

## Out of Scope

- **Full gene properties** — `get_gene_details` covers edge cases
  (to be retired in D5; `run_cypher` as fallback)
- **Ontology terms** — use `gene_ontology_terms`
- **Homolog groups** — use `gene_homologs`
- **Expression data** — use `differential_expression_by_gene` (E2)

## Status / Prerequisites

- [x] KG spec: not needed — all Gene properties exist
- [x] Scope reviewed with user
- [x] Result-size controls decided (batch tool: summary + limit)
- [ ] Ready for Phase 2 (build)

## Use cases

- **Post-discovery routing** — after `resolve_gene`, `genes_by_function`,
  `genes_by_ontology`, or `gene_homologs`, check what data exists for
  each gene before choosing next steps
- **Batch triage** — given 50 genes from an experiment, quickly see
  which have expression data, which have ontology annotations, which
  have orthologs
- **Chain:** `resolve_gene` / `genes_by_function` → `gene_overview` →
  `gene_ontology_terms` / `gene_homologs` / `differential_expression_by_gene`

## KG dependencies

- `Gene` nodes: `locus_tag`, `gene_name`, `product`, `gene_summary`,
  `gene_category`, `annotation_quality`, `organism_strain`,
  `annotation_types`, `expression_edge_count`,
  `significant_expression_count`, `closest_ortholog_group_size`,
  `closest_ortholog_genera`

All properties verified present in live KG (2026-03-23).

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes"},
    annotations={"readOnlyHint": True},
)
async def gene_overview(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Gene locus tags to look up. "
        "E.g. ['PMM0001', 'PMM0845'].",
    )],
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include gene_summary, function_description, all_identifiers.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GeneOverviewResponse:
    """Get an overview of genes: identity and data availability signals.

    Use after resolve_gene, genes_by_function, genes_by_ontology, or
    gene_homologs to understand what each gene is and what follow-up
    data exists.
    """
```

**Return envelope:** `total_matching, by_organism, by_category, by_annotation_type, has_expression, has_significant_expression, has_orthologs, has_clusters, returned, truncated, not_found, results`

**Per-result columns (compact — 13):**
`locus_tag`, `gene_name`, `product`, `gene_category`,
`annotation_quality`, `organism_strain`, `annotation_types`,
`expression_edge_count`, `significant_expression_count`,
`closest_ortholog_group_size`, `closest_ortholog_genera`,
`cluster_membership_count`, `cluster_types`

**Verbose adds (3):**
`gene_summary`, `function_description`, `all_identifiers`

## Result-size controls

Batch input can be large → summary + limit pattern.

### Summary fields (always present)

| Field | Type | Description |
|---|---|---|
| `total_matching` | int | Genes found in KG from input locus_tags |
| `by_organism` | list | Gene counts per organism, sorted desc |
| `by_category` | list | Gene counts per gene_category, sorted desc |
| `by_annotation_type` | list | Gene counts per annotation type (e.g. go_bp, ec, kegg), sorted desc (→ gene_ontology_terms) |
| `has_expression` | int | Genes with expression_edge_count > 0 (→ differential_expression_by_gene) |
| `has_significant_expression` | int | Genes with significant_expression_count > 0 |
| `has_orthologs` | int | Genes with closest_ortholog_group_size > 0 (→ gene_homologs) |
| `has_clusters` | int | Genes with cluster_membership_count > 0 (→ gene_clusters_by_gene) |

### Batch handling

| Field | Type | Description |
|---|---|---|
| `not_found` | list[str] | Input locus_tags that don't exist in KG |

No `no_groups` equivalent needed — every gene in the KG has an overview.

**Sort key:** `locus_tag ASC`

**Default limit:** 5 (MCP), None (api/)

**Verbose:**
- Compact: locus_tag, gene_name, product, gene_category,
  annotation_quality, organism_strain, annotation_types,
  expression_edge_count, significant_expression_count,
  closest_ortholog_group_size, closest_ortholog_genera
- Verbose adds: gene_summary, function_description, all_identifiers

## Special handling

- **2-query pattern:** summary query always runs (OPTIONAL MATCH for
  not_found + apoc breakdowns), detail query skipped when `limit=0`
- **No Lucene:** no fulltext search
- **No caching:** result depends on input locus_tags
- **Validation:** `locus_tags` must be non-empty

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_gene_overview()` (update) + `build_gene_overview_summary()` (new) |
| 2 | API function | `api/functions.py` | `gene_overview()` (rewrite: `list[dict]` → `dict` envelope) |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Verify existing exports (no change expected) |
| 4 | MCP wrapper | `mcp_server/tools.py` | Rewrite: `async def`, Pydantic models, `ToolError` |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | Replace `TestBuildGeneOverview` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | Replace `TestGeneOverview` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | Replace `TestGeneOverviewWrapper` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Update response shape |
| 9 | Regression | `tests/regression/test_regression.py` | Update `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | Update params + shape |
| 11 | About content | `multiomics_explorer/inputs/tools/gene_overview.yaml` | Input YAML → build → verify |
| 12 | Docs | `CLAUDE.md` | Update tool description |
| 13 | Code review | — | Run code-review skill (full checklist) |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_gene_overview_summary`

```python
def build_gene_overview_summary(
    *,
    locus_tags: list[str],
) -> tuple[str, dict]:
    """Build summary + not_found for gene_overview.

    RETURN keys: total_matching, by_organism, by_category,
    by_annotation_type, has_expression, has_significant_expression,
    has_orthologs, has_clusters, not_found.
    """
```

Cypher:
```cypher
UNWIND $locus_tags AS lt
OPTIONAL MATCH (g:Gene {locus_tag: lt})
WITH collect(lt) AS all_tags,
     collect(g) AS genes,
     collect(CASE WHEN g IS NULL THEN lt END) AS not_found_raw
WITH [x IN not_found_raw WHERE x IS NOT NULL] AS not_found,
     [g IN genes WHERE g IS NOT NULL] AS found
WITH not_found, found,
     size(found) AS total_matching,
     [g IN found | g.organism_strain] AS orgs,
     [g IN found | g.gene_category] AS cats,
     apoc.coll.flatten([g IN found | g.annotation_types]) AS all_atypes
RETURN total_matching,
       apoc.coll.frequencies(orgs) AS by_organism,
       apoc.coll.frequencies(cats) AS by_category,
       apoc.coll.frequencies(all_atypes) AS by_annotation_type,
       size([g IN found WHERE g.expression_edge_count > 0]) AS has_expression,
       size([g IN found WHERE g.significant_expression_count > 0]) AS has_significant_expression,
       size([g IN found WHERE g.closest_ortholog_group_size > 0]) AS has_orthologs,
       size([g IN found WHERE g.cluster_membership_count > 0]) AS has_clusters,
       not_found
```

### `build_gene_overview`

```python
def build_gene_overview(
    *,
    locus_tags: list[str],
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_overview.

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    annotation_quality, organism_strain, annotation_types,
    expression_edge_count, significant_expression_count,
    closest_ortholog_group_size, closest_ortholog_genera,
    cluster_membership_count, cluster_types.
    RETURN keys (verbose): adds gene_summary, function_description,
    all_identifiers.
    """
```

Cypher:
```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.gene_category AS gene_category,
       g.annotation_quality AS annotation_quality,
       g.organism_strain AS organism_strain,
       g.annotation_types AS annotation_types,
       g.expression_edge_count AS expression_edge_count,
       g.significant_expression_count AS significant_expression_count,
       g.closest_ortholog_group_size AS closest_ortholog_group_size,
       g.closest_ortholog_genera AS closest_ortholog_genera,
       coalesce(g.cluster_membership_count, 0) AS cluster_membership_count,
       coalesce(g.cluster_types, []) AS cluster_types
       [, g.gene_summary AS gene_summary,               -- verbose only
          g.function_description AS function_description,
          g.all_identifiers AS all_identifiers]
ORDER BY g.locus_tag
[LIMIT $limit]  -- when limit is not None
```

**Design notes:**
- Param renamed from `gene_ids` to `locus_tags` (v3 convention)
- `gene_summary` moved to verbose-only — it's a concatenated text field
  that adds bulk without aiding routing decisions
- `function_description` in verbose — consistent with `genes_by_function`
- `all_identifiers` in verbose — cross-references (UniProt, CyanorakID,
  RefSeq) replace the main use case of `get_gene_details`
- Summary builder uses OPTIONAL MATCH to detect not_found tags

---

## API Function

**File:** `api/functions.py`

```python
def gene_overview(
    locus_tags: list[str],
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get overview of genes: identity + data availability signals.

    Returns dict with keys: total_matching, by_organism, by_category,
    by_annotation_type, has_expression, has_significant_expression,
    has_orthologs, has_clusters, returned, truncated, not_found, results.
    Per result: locus_tag, gene_name, product, gene_category,
    annotation_quality, organism_strain, annotation_types,
    expression_edge_count, significant_expression_count,
    closest_ortholog_group_size, closest_ortholog_genera,
    cluster_membership_count, cluster_types.
    Verbose adds: gene_summary, function_description, all_identifiers.
    """
```

- **Breaking change:** returns `dict` instead of `list[dict]`
- **Breaking change:** param renamed from `gene_ids` to `locus_tags`
- `summary=True` → `limit=0`
- Always run summary query → total_matching, breakdowns, not_found
- Skip detail when `limit=0`
- Rename APOC `{item, count}` to domain keys via `_rename_freq()` helper
  (same pattern as `genes_by_function`), sort desc
- Summary query returns single row: `conn.execute_query(...)[0]`

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

Pydantic response models:

```python
class GeneOverviewResult(BaseModel):
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
    gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
    product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III subunit beta')")
    gene_category: str | None = Field(default=None, description="Functional category (e.g. 'Replication and repair')")
    annotation_quality: int | None = Field(default=None, description="Annotation quality score 0-3 (e.g. 3)")
    organism_strain: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
    annotation_types: list[str] = Field(default_factory=list, description="Ontology types with annotations (e.g. ['go_bp', 'ec', 'kegg'])")
    expression_edge_count: int = Field(default=0, description="Number of expression data points (e.g. 36)")
    significant_expression_count: int = Field(default=0, description="Significant DE observations (e.g. 5)")
    closest_ortholog_group_size: int | None = Field(default=None, description="Size of tightest ortholog group (e.g. 9)")
    closest_ortholog_genera: list[str] | None = Field(default=None, description="Genera in tightest ortholog group (e.g. ['Prochlorococcus', 'Synechococcus'])")
    cluster_membership_count: int = Field(default=0, description="Number of cluster memberships (e.g. 3)")
    cluster_types: list[str] = Field(default_factory=list, description="Distinct cluster types (e.g. ['condition_comparison', 'diel'])")
    # verbose-only
    gene_summary: str | None = Field(default=None, description="Concatenated summary text (e.g. 'dnaN :: DNA polymerase III subunit beta :: Alternative locus ID')")
    function_description: str | None = Field(default=None, description="Curated functional description (e.g. 'Alternative locus ID')")
    all_identifiers: list[str] | None = Field(default=None, description="Cross-references: UniProt, CyanorakID, RefSeq, etc. (e.g. ['CK_Pro_MED4_00845', 'Q7V1M0', 'WP_011132479.1'])")

class OverviewOrganismBreakdown(BaseModel):
    organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
    count: int = Field(description="Genes from this organism (e.g. 3)")

class OverviewCategoryBreakdown(BaseModel):
    category: str = Field(description="Gene category (e.g. 'Photosynthesis')")
    count: int = Field(description="Genes in this category (e.g. 5)")

class OverviewAnnotationTypeBreakdown(BaseModel):
    annotation_type: str = Field(description="Ontology type (e.g. 'go_bp', 'ec', 'kegg')")
    count: int = Field(description="Genes with this annotation type (e.g. 12)")

class GeneOverviewResponse(BaseModel):
    total_matching: int = Field(description="Genes found in KG from input locus_tags")
    by_organism: list[OverviewOrganismBreakdown] = Field(description="Gene counts per organism, sorted desc")
    by_category: list[OverviewCategoryBreakdown] = Field(description="Gene counts per category, sorted desc")
    by_annotation_type: list[OverviewAnnotationTypeBreakdown] = Field(description="Gene counts per annotation type, sorted desc")
    has_expression: int = Field(description="Genes with expression data (expression_edge_count > 0)")
    has_significant_expression: int = Field(description="Genes with significant DE observations")
    has_orthologs: int = Field(description="Genes with ortholog group membership")
    has_clusters: int = Field(description="Genes with cluster membership")
    returned: int = Field(description="Results in this response (0 when summary=true)")
    truncated: bool = Field(description="True if total_matching > returned")
    not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
    results: list[GeneOverviewResult] = Field(default_factory=list, description="One row per gene")
```

Breakdown models follow the per-tool prefix convention
(`FunctionOrganismBreakdown`, `HomologOrganismBreakdown`, etc.) —
no shared models between tools.

### Wrapper

```python
@mcp.tool(
    tags={"genes"},
    annotations={"readOnlyHint": True},
)
async def gene_overview(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Gene locus tags to look up. "
        "E.g. ['PMM0001', 'PMM0845'].",
    )],
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include gene_summary, function_description, all_identifiers.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GeneOverviewResponse:
    """Get an overview of genes: identity and data availability signals.

    Use after resolve_gene, genes_by_function, genes_by_ontology, or
    gene_homologs to understand what each gene is and what follow-up
    data exists.
    """
    await ctx.info(f"gene_overview locus_tags={locus_tags} summary={summary}")
    try:
        conn = _conn(ctx)
        data = api.gene_overview(
            locus_tags, summary=summary, verbose=verbose,
            limit=limit, conn=conn,
        )
        by_organism = [OverviewOrganismBreakdown(**b) for b in data["by_organism"]]
        by_category = [OverviewCategoryBreakdown(**b) for b in data["by_category"]]
        by_annotation_type = [OverviewAnnotationTypeBreakdown(**b) for b in data["by_annotation_type"]]
        results = [GeneOverviewResult(**r) for r in data["results"]]
        return GeneOverviewResponse(
            total_matching=data["total_matching"],
            by_organism=by_organism,
            by_category=by_category,
            by_annotation_type=by_annotation_type,
            has_expression=data["has_expression"],
            has_significant_expression=data["has_significant_expression"],
            has_orthologs=data["has_orthologs"],
            has_clusters=data["has_clusters"],
            returned=data["returned"],
            truncated=data["truncated"],
            not_found=data["not_found"],
            results=results,
        )
    except ValueError as e:
        await ctx.warning(f"gene_overview error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"gene_overview unexpected error: {e}")
        raise ToolError(f"Error in gene_overview: {e}")
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

Replace `TestBuildGeneOverview` with:

```
class TestBuildGeneOverview:
    test_returns_expected_columns
    test_verbose_false (no gene_summary)
    test_verbose_true (gene_summary present)
    test_limit_clause
    test_limit_none
    test_order_by

class TestBuildGeneOverviewSummary:
    test_returns_summary_keys
    test_not_found_logic (OPTIONAL MATCH)
```

### Unit: API function (`test_api_functions.py`)

Replace `TestGeneOverview` with:

```
class TestGeneOverview:
    test_returns_dict (not list)
    test_summary_sets_limit_zero
    test_passes_params (locus_tags, verbose, limit)
    test_creates_conn_when_none
    test_not_found_populated
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

Replace `TestGeneOverviewWrapper` with:

```
class TestGeneOverviewWrapper:
    test_returns_dict_envelope
    test_empty_results (not_found populated)
    test_params_forwarded (locus_tags, summary, verbose, limit)
    test_truncation_metadata
```

Update `EXPECTED_TOOLS` (tool name unchanged).

### Integration (`test_mcp_tools.py`)

Against live KG:
- Batch query returns expected fields in dict envelope
- Not-found gene returns `not_found` populated
- Each result has expected compact columns

### Regression (`test_regression.py`)

Update `TOOL_BUILDERS` (builder signature changed: `gene_ids` → `locus_tags`):
```python
"gene_overview": build_gene_overview,
```

### Eval cases (`cases.yaml`)

```yaml
- id: gene_overview_single_pro
  tool: gene_overview
  desc: Single Prochlorococcus gene overview with routing signals
  params:
    locus_tags: ["PMM1428"]
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, gene_category,
              annotation_quality, organism_strain, annotation_types,
              expression_edge_count, significant_expression_count,
              closest_ortholog_group_size, closest_ortholog_genera]

- id: gene_overview_single_alt
  tool: gene_overview
  desc: Single Alteromonas gene overview
  params:
    locus_tags: ["EZ55_00275"]
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain]

- id: gene_overview_batch
  tool: gene_overview
  desc: Batch overview for Pro + Alt genes
  params:
    locus_tags: ["PMM1428", "EZ55_00275"]
  expect:
    min_rows: 2
    columns: [locus_tag, gene_summary, annotation_types]

- id: gene_overview_regression_pro
  tool: gene_overview
  desc: Gene overview regression baseline for Pro gene
  params:
    locus_tags: ["PMM1428"]

- id: gene_overview_regression_alt
  tool: gene_overview
  desc: Gene overview regression baseline for Alt gene
  params:
    locus_tags: ["EZ55_00275"]
```

Regenerate regression baselines: `pytest tests/regression/ --force-regen -m kg`

---

## About Content

### Input YAML

**File:** `multiomics_explorer/inputs/tools/gene_overview.yaml`

```yaml
examples:
  - title: Overview of a single gene
    call: gene_overview(locus_tags=["PMM1428"])
    response: |
      {
        "total_matching": 1,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
        "by_category": [{"category": "Unknown", "count": 1}],
        "by_annotation_type": [{"annotation_type": "go_mf", "count": 1}, {"annotation_type": "pfam", "count": 1}, ...],
        "has_expression": 1, "has_significant_expression": 1, "has_orthologs": 1, "has_clusters": 1,
        "returned": 1, "truncated": false, "not_found": [],
        "results": [
          {"locus_tag": "PMM1428", "gene_name": null, "product": "EVE domain protein",
           "gene_category": "Unknown", "annotation_quality": 3,
           "organism_strain": "Prochlorococcus MED4",
           "annotation_types": ["go_mf", "pfam", "cog_category", "tigr_role"],
           "expression_edge_count": 36, "significant_expression_count": 5,
           "closest_ortholog_group_size": 9,
           "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
           "cluster_membership_count": 2, "cluster_types": ["condition_comparison"]}
        ]
      }

  - title: Batch overview with mixed organisms
    call: gene_overview(locus_tags=["PMM1428", "EZ55_00275"])

  - title: Summary only (counts and breakdowns)
    call: gene_overview(locus_tags=["PMM0845", "PMM1428", "EZ55_00275"], summary=True)

  - title: From discovery to overview to details
    steps: |
      Step 1: genes_by_function(search_text="photosystem")
              → collect locus_tags from results

      Step 2: gene_overview(locus_tags=["PMM0845", ...])
              → check which genes have expression data, ontology, orthologs

      Step 3: gene_ontology_terms(locus_tags=["PMM0845"])
              → drill into annotations for genes with rich annotation_types

verbose_fields:
  - gene_summary
  - function_description
  - all_identifiers

chaining:
  - "resolve_gene → gene_overview"
  - "genes_by_function → gene_overview"
  - "gene_overview → gene_ontology_terms"
  - "gene_overview → gene_homologs"
  - "gene_overview → differential_expression_by_gene"

mistakes:
  - "annotation_types lists which ontology types have data — use gene_ontology_terms to get the actual terms"
  - "expression_edge_count > 0 means expression data exists — use differential_expression_by_gene to explore it"
  - "closest_ortholog_genera shows cross-genus reach — use gene_homologs for full group membership"
  - wrong: "gene_overview(locus_tags=['PMM0845'], verbose=True)  # just to see the gene"
    right: "gene_overview(locus_tags=['PMM0845'])  # verbose only needed for gene_summary text"
```

### Build

```bash
uv run python scripts/build_about_content.py gene_overview
```

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Documentation

- `CLAUDE.md`: already has gene_overview — update description to mention
  batch, summary fields

## Code Review

Run code-review skill (full checklist) as final step.
