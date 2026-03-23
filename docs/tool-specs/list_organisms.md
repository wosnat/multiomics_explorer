# Tool spec: `list_organisms` — update existing tool

List all organisms with genome data in the KG. This is a discovery tool —
researchers call it first to see what's available, then use organism names
to filter other tools. Currently returns minimal columns; updating to
include species, taxonomy IDs, and data-availability signals.

## Out of Scope

- Filtering by genus/clade/phylum — Claude can filter in context.
- Summary/detail modes — not needed for this tool.
- Per-gene expression data — requires joining through Gene →
  Changes_expression_of, use `list_publications(organism=...)` instead.

## Status / Prerequisites

- [x] KG spec complete: `docs/kg-specs/kg-spec-list-organisms.md`
- [x] KG changes landed and verified (2026-03-22)
- [x] Scope reviewed with user
- [x] Result-size controls decided: verbose + limit (no modes)
- [x] Ready for Phase 2 (build)

## Use cases

- **Discovery:** "What organisms are in this KG?" — first tool a
  researcher calls, orients all subsequent queries.
- **Filter value lookup:** organism names returned here are used as
  filter values in `genes_by_function`, `resolve_gene`, `genes_by_ontology`,
  `list_publications`, etc.
- **Cross-referencing:** `ncbi_taxon_id` enables lookup in NCBI,
  UniProt, JGI, etc.
- **Chaining:** `list_organisms` → pick organism → `genes_by_function(organism=...)`
  or `list_publications(organism=...)`.

## KG dependencies

- `OrganismTaxon` nodes with properties: `preferred_name`, `genus`,
  `strain_name`, `clade`, `species`, `ncbi_taxon_id`
- Precomputed properties on OrganismTaxon: `gene_count`,
  `publication_count`, `experiment_count`, `treatment_types`, `omics_types`
- KG spec: `docs/kg-specs/kg-spec-list-organisms.md`

---

## Tool Signature

```python
@mcp.tool(
    tags={"organisms", "discovery"},
    annotations={"readOnlyHint": True},
)
async def list_organisms(
    ctx: Context,
    verbose: Annotated[bool, Field(
        description="Include full taxonomy hierarchy "
        "(family, order, class, phylum, kingdom, superkingdom, lineage).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 50,
) -> ListOrganismsResponse:
    """List all organisms with sequenced genomes in the knowledge graph.

    Returns taxonomy, gene counts, and publication counts for each organism.
    Use the returned organism names as filter values in genes_by_function,
    resolve_gene, genes_by_ontology, list_publications, etc. The organism
    filter uses partial matching — "MED4", "Prochlorococcus MED4", and
    "Prochlorococcus" all work.
    """
```

Two parameters (`verbose`, `limit`). Currently small result set (~13
organisms with genes, ~18 total), but expected to grow as more genomes
are added.

**Return envelope:** `{total_entries, returned, truncated, results: [...]}`

**Per-result columns (compact):**

| Field | Type | Description |
|---|---|---|
| organism_name | str | Display name (e.g. "Prochlorococcus MED4"). Use for organism filters in other tools. |
| genus | str \| null | Genus (e.g. "Prochlorococcus", "Alteromonas") |
| species | str \| null | Binomial species name (e.g. "Prochlorococcus marinus") |
| strain | str \| null | Strain identifier (e.g. "MED4", "EZ55") |
| clade | str \| null | Ecotype clade, Prochlorococcus-specific (e.g. "HLI", "LLIV") |
| ncbi_taxon_id | int \| null | NCBI Taxonomy ID for cross-referencing external databases |
| gene_count | int | Number of Gene nodes in the KG for this organism |
| publication_count | int | Number of publications studying this organism |
| experiment_count | int | Total experiments across all publications for this organism |
| treatment_types | list[str] | Distinct treatment types studied (e.g. ["coculture", "light_stress"]) |
| omics_types | list[str] | Distinct omics types available (e.g. ["RNASEQ", "PROTEOMICS"]) |

**Verbose adds:**

| Field | Type | Description |
|---|---|---|
| family | str \| null | Taxonomic family (e.g. "Prochlorococcaceae") |
| order | str \| null | Taxonomic order (e.g. "Synechococcales") |
| tax_class | str \| null | Taxonomic class (e.g. "Cyanophyceae") |
| phylum | str \| null | Taxonomic phylum (e.g. "Cyanobacteriota") |
| kingdom | str \| null | Taxonomic kingdom (e.g. "Bacillati") |
| superkingdom | str \| null | Taxonomic superkingdom (e.g. "Bacteria") |
| lineage | str \| null | Full NCBI taxonomy lineage string |

## Result-size controls

### Option A: Small result set (no modes needed)

Currently small (~18 rows), growing as genomes are added.
No summary/detail modes.

**Sort key:** `genus ASC, organism_name ASC` (groups genera together,
alphabetical within genus)

**Default limit:** 50

**Verbose:** yes — controls whether full taxonomy hierarchy is included.
- Compact (default): organism_name, genus, species, strain, clade,
  ncbi_taxon_id, gene_count, publication_count, experiment_count,
  treatment_types, omics_types
- Verbose adds: family, order, tax_class, phylum, kingdom,
  superkingdom, lineage

## Special handling

- **Caching:** No — query reads precomputed properties from ~15 nodes,
  trivially fast even over remote connection. Not worth the complexity.
- **No filtering** — returns all organisms. Claude filters in context.

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | Update `build_list_organisms(verbose)` — read precomputed stats + taxonomy, verbose columns |
| 2 | API function | `api/functions.py` | Update `list_organisms(verbose)` signature + return docstring |
| 3 | MCP wrapper | `mcp_server/tools.py` | Pydantic models, async, ToolError, tags, verbose param, updated docstring |
| 4 | Unit tests | All three test files | Update test data and assertions for new columns |
| 5 | Integration | `tests/integration/test_mcp_tools.py` | Verify against live KG |
| 6 | Regression | `tests/regression/test_regression.py` | Update baseline |
| 7 | About content | `multiomics_explorer/skills/.../tools/list_organisms.md` | Per-tool about text |
| 8 | Docs | `CLAUDE.md` | Update tool table description |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_list_organisms`

```python
def build_list_organisms(
    *,
    verbose: bool = False,
) -> tuple[str, dict]:
    """Build Cypher for listing all organisms with data-availability signals.

    RETURN keys (compact): organism_name, genus, species, strain, clade,
    ncbi_taxon_id, gene_count, publication_count, experiment_count,
    treatment_types, omics_types.
    RETURN keys (verbose): adds family, order, tax_class, phylum, kingdom,
    superkingdom, lineage.
    """
```

**Cypher:**

```cypher
MATCH (o:OrganismTaxon)
RETURN o.preferred_name AS organism_name,
       o.genus AS genus,
       o.species AS species,
       o.strain_name AS strain,
       o.clade AS clade,
       o.ncbi_taxon_id AS ncbi_taxon_id,
       o.gene_count AS gene_count,
       o.publication_count AS publication_count,
       o.experiment_count AS experiment_count,
       o.treatment_types AS treatment_types,
       o.omics_types AS omics_types
       {verbose_columns}
ORDER BY o.genus, o.preferred_name
```

`{verbose_columns}` expands to:
```
,      o.family AS family,
       o.order AS order,
       o.tax_class AS tax_class,
       o.phylum AS phylum,
       o.kingdom AS kingdom,
       o.superkingdom AS superkingdom,
       o.lineage AS lineage
```
when `verbose=True`, empty string otherwise.

No LIMIT in Cypher — limit is applied in Python (API layer slices
the result list) so `total_entries` can be computed from the full set.

**Design notes:**
- All stats are precomputed on OrganismTaxon nodes during KG build
  (see KG spec). No joins needed — single MATCH, property reads only.
- Same pattern as Publication nodes with precomputed `experiment_count`,
  `treatment_types`, `omics_types`.
- No WHERE clause — returns all organisms.

---

## API Function

**File:** `api/functions.py`

```python
def list_organisms(
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List all organisms in the knowledge graph.

    Returns dict with keys: total_entries, results.
    Per result: organism_name, genus, species, strain, clade,
    ncbi_taxon_id, gene_count, publication_count, experiment_count,
    treatment_types, omics_types.
    When verbose=True, also includes: family, order, tax_class, phylum,
    kingdom, superkingdom, lineage.
    """
    conn = _default_conn(conn)
    # Get all rows (no limit) to count total, then slice
    cypher, params = build_list_organisms(verbose=verbose)
    all_results = conn.execute_query(cypher, **params)
    total = len(all_results)
    results = all_results[:limit] if limit else all_results
    return {"total_entries": total, "results": results}
```

Returns dict with `total_entries` + `results` — single query, slice
for limit in Python. Avoids running two queries.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
class OrganismResult(BaseModel):
    organism_name: str = Field(description="Display name (e.g. 'Prochlorococcus MED4'). Use for organism filters in other tools.")
    genus: str | None = Field(default=None, description="Genus (e.g. 'Prochlorococcus', 'Alteromonas')")
    species: str | None = Field(default=None, description="Binomial species name (e.g. 'Prochlorococcus marinus')")
    strain: str | None = Field(default=None, description="Strain identifier (e.g. 'MED4', 'EZ55')")
    clade: str | None = Field(default=None, description="Ecotype clade, Prochlorococcus-specific (e.g. 'HLI', 'LLIV')")
    ncbi_taxon_id: int | None = Field(default=None, description="NCBI Taxonomy ID for cross-referencing external databases (e.g. 59919)")
    gene_count: int = Field(description="Number of genes in the KG for this organism (e.g. 1976)")
    publication_count: int = Field(description="Number of publications studying this organism (e.g. 11)")
    experiment_count: int = Field(description="Total experiments across all publications (e.g. 46)")
    treatment_types: list[str] = Field(default_factory=list, description="Distinct treatment types studied (e.g. ['coculture', 'light_stress', 'nitrogen_stress'])")
    omics_types: list[str] = Field(default_factory=list, description="Distinct omics types available (e.g. ['RNASEQ', 'PROTEOMICS'])")
    # verbose-only fields
    family: str | None = Field(default=None, description="Taxonomic family (e.g. 'Prochlorococcaceae')")
    order: str | None = Field(default=None, description="Taxonomic order (e.g. 'Synechococcales')")
    tax_class: str | None = Field(default=None, description="Taxonomic class (e.g. 'Cyanophyceae')")
    phylum: str | None = Field(default=None, description="Taxonomic phylum (e.g. 'Cyanobacteriota')")
    kingdom: str | None = Field(default=None, description="Taxonomic kingdom (e.g. 'Bacillati')")
    superkingdom: str | None = Field(default=None, description="Taxonomic superkingdom (e.g. 'Bacteria')")
    lineage: str | None = Field(default=None, description="Full NCBI taxonomy lineage string (e.g. 'cellular organisms; Bacteria; ...; Prochlorococcus marinus')")

class ListOrganismsResponse(BaseModel):
    total_entries: int = Field(description="Total organisms in the KG")
    returned: int = Field(description="Number of results returned")
    truncated: bool = Field(description="True if results were truncated by limit")
    results: list[OrganismResult]
```

```python
@mcp.tool(
    tags={"organisms", "discovery"},
    annotations={"readOnlyHint": True},
)
async def list_organisms(
    ctx: Context,
    verbose: Annotated[bool, Field(
        description="Include full taxonomy hierarchy "
        "(family, order, class, phylum, kingdom, superkingdom, lineage).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 50,
) -> ListOrganismsResponse:
    """List all organisms with sequenced genomes in the knowledge graph.

    Returns taxonomy, gene counts, and publication counts for each organism.
    Use the returned organism names as filter values in genes_by_function,
    resolve_gene, genes_by_ontology, list_publications, etc. The organism
    filter uses partial matching — "MED4", "Prochlorococcus MED4", and
    "Prochlorococcus" all work.
    """
    await ctx.info(f"list_organisms verbose={verbose} limit={limit}")
    try:
        conn = _conn(ctx)
        result = api.list_organisms(verbose=verbose, limit=limit, conn=conn)
        organisms = [OrganismResult(**r) for r in result["results"]]
        response = ListOrganismsResponse(
            total_entries=result["total_entries"],
            returned=len(organisms),
            truncated=result["total_entries"] > len(organisms),
            results=organisms,
        )
        await ctx.info(f"Returning {response.returned} of {response.total_entries} organisms")
        return response
    except Exception as e:
        await ctx.error(f"list_organisms unexpected error: {e}")
        raise ToolError(f"Error in list_organisms: {e}")
```

No caching — query is trivially fast with precomputed stats.
Switch from returning JSON string to returning Pydantic model.

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildListOrganisms:
    test_returns_expected_columns  — compact 11 columns present in RETURN
    test_verbose_false             — no taxonomy hierarchy columns in RETURN
    test_verbose_true              — family, order, tax_class, etc. in RETURN
    test_order_by                  — ORDER BY genus, preferred_name
    test_reads_precomputed_props   — Cypher reads o.gene_count, o.publication_count, etc. (no joins)
```

### Unit: API function (`test_api_functions.py`)

```
class TestListOrganisms:
    test_returns_dict              — returns dict with total_entries, results
    test_passes_verbose            — verbose forwarded to builder
    test_limit_slices_results      — limit=N returns first N results, total_entries is full count
    test_limit_none                — no limit returns all results
    test_creates_conn_when_none    — default conn used when None
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestListOrganismsWrapper:
    test_returns_response_envelope — response has total_entries, returned, truncated, results
    test_expected_columns_compact  — compact result has 11 fields, no taxonomy hierarchy
    test_expected_columns_verbose  — verbose result includes taxonomy hierarchy fields
    test_empty_results             — returns envelope with total_entries=0
    test_truncation_metadata       — returned == len(results), truncated == (total > returned)
    test_generic_error             — exception raises ToolError
```

---

## About Content

Auto-generated from Pydantic models + human-authored input YAML.
Served via MCP resource at `docs://tools/list_organisms`.

### 1. Create input YAML

```bash
uv run python scripts/build_about_content.py --skeleton list_organisms
```

Edit `multiomics_explorer/inputs/tools/list_organisms.yaml` with:

```yaml
examples:
  - title: Browse all organisms
    call: list_organisms()
    response: |
      {
        "total_entries": 15,
        "returned": 15,
        "truncated": false,
        "results": [
          {"organism_name": "Prochlorococcus MED4", "genus": "Prochlorococcus", "gene_count": 1976, "publication_count": 11, "experiment_count": 46, "treatment_types": ["coculture", "light_stress", ...], ...},
          {"organism_name": "Alteromonas macleodii EZ55", "genus": "Alteromonas", "gene_count": 4136, ...}
        ]
      }

  - title: Full taxonomy
    call: list_organisms(verbose=True)

  - title: Chaining to genes
    steps: |
      Step 1: list_organisms()
              → discover available organisms and data coverage

      Step 2: genes_by_function(search_text="photosystem", organism="MED4")
              → search genes within a specific organism

      Step 3: list_publications(organism="MED4")
              → find publications studying that organism

chaining:
  - "list_organisms → genes_by_function"
  - "list_organisms → list_publications"
  - "list_organisms → resolve_gene"
  - "list_organisms → genes_by_ontology"

mistakes:
  - "gene_count and publication_count are counts of data in the KG, not biological totals"
  - "Organisms with gene_count=0 are parent/umbrella taxonomy nodes (e.g. genus-level 'Alteromonas')"
```

### 2. Build

```bash
uv run python scripts/build_about_content.py list_organisms
```

Output: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_organisms.md`

### 3. Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Update tool table: `list_organisms` — All organisms with taxonomy, gene counts, publication counts |
