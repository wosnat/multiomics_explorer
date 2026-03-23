# Tool spec: genes_by_ontology

## Purpose

Find genes annotated to ontology term IDs, with hierarchy expansion.
Discovery tool in the Phase 2 ontology triplet:
`search_ontology` → `genes_by_ontology` → `gene_ontology_terms`.

Not a rename — same name, v3 upgrade.

## Out of Scope

- **Term discovery** — use `search_ontology` to find term IDs first
- **Per-gene ontology details** — use `gene_ontology_terms` for reverse
  lookup (gene → terms)
- **Free-text gene search** — use `genes_by_function` for Lucene search
  across gene annotations
- **Gene routing signals** — use `gene_overview` after this tool to check
  expression/homology availability

## Status / Prerequisites

- [x] KG spec: not needed — existing hierarchy relationships suffice
- [x] Scope reviewed with user
- [x] Result-size controls decided (summary + verbose + limit)
- [ ] Ready for Phase 2 (build)

## Use cases

- **Ontology-driven discovery** — "which genes are annotated to
  GO:0006260 (DNA replication)?" → get gene list with organism breakdown
- **Cross-term comparison** — pass multiple term IDs, use `by_term`
  summary to compare gene counts per term
- **Organism-scoped query** — filter by organism to focus on one strain
- **Chain:** `search_ontology` → `genes_by_ontology` → `gene_overview`

## KG dependencies

**Existing (no changes needed):**
- `ONTOLOGY_CONFIG` in `kg/queries_lib.py`: all 9 ontology types with
  labels, gene relationships, hierarchy relationships, level filters
- Node labels: BiologicalProcess, MolecularFunction, CellularComponent,
  EcNumber, KeggTerm, CogFunctionalCategory, CyanorakRole, TigrRole,
  Pfam, PfamClan
- Gene properties: `locus_tag`, `gene_name`, `product`,
  `organism_strain`, `gene_category`, `gene_summary`,
  `function_description` (all verified present 2026-03-23)

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes", "ontology"},
    annotations={"readOnlyHint": True},
)
async def genes_by_ontology(
    ctx: Context,
    term_ids: Annotated[list[str], Field(
        description="Ontology term IDs (from search_ontology). "
        "E.g. ['go:0006260', 'go:0006412'].",
    )],
    ontology: Annotated[Literal[
        "go_bp", "go_mf", "go_cc", "kegg", "ec",
        "cog_category", "cyanorak_role", "tigr_role", "pfam",
    ], Field(
        description="Ontology the term IDs belong to.",
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
        description="Include matched_terms, gene_summary, function_description.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GenesByOntologyResponse:
    """Find genes annotated to ontology terms, with hierarchy expansion.

    Takes term IDs from search_ontology and finds all genes annotated to
    those terms or any descendant terms in the ontology hierarchy.
    Results are distinct genes (deduplicated across terms).

    For term discovery, use search_ontology first.
    For per-gene ontology details, use gene_ontology_terms.
    """
```

**Return envelope:** `total_matching, by_organism, by_category, by_term, returned, truncated, results`

**Per-result columns (compact — 5):**
`locus_tag`, `gene_name`, `product`, `organism_strain`, `gene_category`

**Verbose adds (3):**
`matched_terms`, `gene_summary`, `function_description`

## Result-size controls

Frequently large (411 genes for one GO term, 1742 for two) → summary +
verbose + limit.

### Summary fields (always present)

| Field | Type | Description |
|---|---|---|
| `total_matching` | int | Distinct genes matching all input terms + organism filter |
| `by_organism` | list | Gene counts per organism, sorted desc |
| `by_category` | list | Gene counts per gene_category, sorted desc |
| `by_term` | list | Gene counts per input term_id, sorted desc (can overlap — a gene matching 2 terms is counted in both) |

### Detail mode

| Field | Type | Description |
|---|---|---|
| `locus_tag` | str | Gene locus tag (e.g. `'PMM0001'`) |
| `gene_name` | str \| None | Gene name (e.g. `'dnaN'`) |
| `product` | str \| None | Gene product (e.g. `'DNA polymerase III, beta subunit'`) |
| `organism_strain` | str | Organism (e.g. `'Prochlorococcus MED4'`) |
| `gene_category` | str \| None | Functional category (e.g. `'Replication and repair'`) |

### Verbose adds

| Field | Type | Description |
|---|---|---|
| `matched_terms` | list[str] | Input term IDs this gene was matched through (e.g. `['go:0006260']`) |
| `gene_summary` | str \| None | Concatenated summary text |
| `function_description` | str \| None | Curated functional description |

### Zero-match behavior

When `total_matching=0`: all summary fields present, counts are 0,
`by_organism=[]`, `by_category=[]`, `by_term=[]`, `results=[]`,
`returned=0`, `truncated=False`.

**Sort key:** `organism_strain ASC, locus_tag ASC`

**Default limit:** 5 (MCP), None (api/)

## Special handling

- **Hierarchy expansion:** each input term is expanded to all descendants
  via `*0..15` variable-length relationship traversal (existing pattern)
- **KEGG level filter:** KEGG terms have a `gene_connects_to_level` filter
  that restricts descendants to `ko` level only (existing pattern)
- **Pfam parent label:** Pfam searches both `Pfam` and `PfamClan` labels
  (existing pattern)
- **Deduplication:** results are DISTINCT genes — a gene matching multiple
  input terms appears once. `by_term` summary tracks per-term counts
  before dedup
- **No Lucene:** no fulltext search, no retry logic
- **Validation:** `ontology` validated by `Literal` type at MCP layer
  (Pydantic rejects invalid values before the call reaches api/); builder
  still validates as a safety net. `term_ids` raises `ValueError` if empty
- **Backport:** `search_ontology` and `gene_ontology_terms` should also
  switch `ontology` from `str` to `Literal` for consistency (separate change)

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_genes_by_ontology()` (update: add verbose, limit) + `build_genes_by_ontology_summary()` (new) |
| 2 | API function | `api/functions.py` | `genes_by_ontology()` (rewrite: `list[dict]` → `dict` envelope, 2-query pattern) |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Verify existing exports (no change expected) |
| 4 | MCP wrapper | `mcp_server/tools.py` | Rewrite: `async def`, Pydantic models, `ToolError` |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | Replace `TestBuildGenesByOntology` + add `TestBuildGenesByOntologySummary` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | Replace `TestGenesByOntology` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | Replace `TestGenesByOntologyWrapper` |
| 8 | Integration | `tests/integration/test_tool_correctness_kg.py` | Update response shape |
| 9 | Regression | `tests/regression/test_regression.py` | Update `TOOL_BUILDERS` (signature changed) |
| 10 | Eval cases | `tests/evals/cases.yaml` | Update params + shape |
| 11 | About content | `multiomics_explorer/inputs/tools/genes_by_ontology.yaml` | Input YAML → build → verify |
| 12 | Docs | `CLAUDE.md` | Update tool description |
| 13 | Code review | — | Run code-review skill |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_genes_by_ontology_summary`

```python
def build_genes_by_ontology_summary(
    *,
    ontology: str,
    term_ids: list[str],
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_ontology.

    RETURN keys: total_matching, by_organism, by_category, by_term.
    """
```

Cypher (example for go_bp):
```cypher
UNWIND $term_ids AS tid
MATCH (root:BiologicalProcess) WHERE root.id = tid
MATCH (root)<-[:Biological_process_is_a_biological_process
              |Biological_process_part_of_biological_process*0..15]-(descendant)
WITH DISTINCT descendant, tid AS root_tid
MATCH (g:Gene)-[:Gene_involved_in_biological_process]->(descendant)
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
WITH DISTINCT root_tid, g.locus_tag AS lt, g.organism_strain AS org,
     coalesce(g.gene_category, 'Unknown') AS cat
WITH collect({lt: lt, org: org, cat: cat, tid: root_tid}) AS rows
WITH rows,
     size(apoc.coll.toSet([r IN rows | r.lt])) AS total_matching,
     apoc.coll.frequencies([r IN rows | r.tid]) AS by_term
// Deduplicate by locus_tag for by_organism / by_category
WITH total_matching, by_term, rows,
     apoc.coll.toSet([r IN rows | r.lt]) AS unique_lts
UNWIND unique_lts AS lt
WITH total_matching, by_term,
     [r IN rows WHERE r.lt = lt][0] AS rep
WITH total_matching, by_term,
     collect(rep.org) AS orgs, collect(rep.cat) AS cats
RETURN total_matching, by_term,
       apoc.coll.frequencies(orgs) AS by_organism,
       apoc.coll.frequencies(cats) AS by_category
```

**Design notes:**
- Deduplicates genes using `apoc.coll.toSet` on locus_tag for
  `total_matching`; picks one representative row per locus_tag for
  `by_organism` and `by_category` (each gene has one organism/category)
- `by_term` counts genes per input term_id before dedup (a gene
  matching 2 terms is counted in both)
- Organism filter applied before aggregation
- Dynamic Cypher generation from `ONTOLOGY_CONFIG` (same pattern as
  existing `build_genes_by_ontology`)
- Pfam uses `(root:{label} OR root:{parent_label})` pattern
- KEGG uses `level_filter` pattern
- Hierarchy-less ontologies (cog_category, tigr_role) use
  `WITH root AS descendant` instead of expansion

### `build_genes_by_ontology`

```python
def build_genes_by_ontology(
    *,
    ontology: str,
    term_ids: list[str],
    organism: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_ontology.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_strain, gene_category.
    RETURN keys (verbose): adds matched_terms, gene_summary,
    function_description.
    """
```

Cypher (compact — same expansion as current, adding limit):
```cypher
{root_match}
{expansion}
{level_clause}
MATCH (g:Gene)-[:{gene_rel}]->(descendant)
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
RETURN DISTINCT g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain,
       g.gene_category AS gene_category
ORDER BY g.organism_strain, g.locus_tag
[LIMIT $limit]  -- when limit is not None
```

Cypher (verbose — tracks matched terms via UNWIND + collect):
```cypher
UNWIND $term_ids AS tid
{root_match_with_tid}
{expansion}
{level_clause}
MATCH (g:Gene)-[:{gene_rel}]->(descendant)
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
WITH DISTINCT tid, g
WITH g, collect(DISTINCT tid) AS matched_terms
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain,
       g.gene_category AS gene_category,
       matched_terms,
       g.gene_summary AS gene_summary,
       g.function_description AS function_description
ORDER BY g.organism_strain, g.locus_tag
[LIMIT $limit]
```

**Design notes:**
- Sort changed from `g.locus_tag` to `g.organism_strain, g.locus_tag`
  (groups by organism for readability)
- `verbose` controls additional RETURN columns (same pattern as
  `genes_by_function`)
- `limit` pushed to Cypher (v3 convention: server-side limiting)
- Existing hierarchy expansion, organism filter, deduplication unchanged

---

## API Function

**File:** `api/functions.py`

```python
def genes_by_ontology(
    term_ids: list[str],
    ontology: str,
    organism: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Find genes annotated to ontology terms, with hierarchy expansion.

    Returns dict with keys: total_matching, by_organism, by_category,
    by_term, returned, truncated, results.
    Per result: locus_tag, gene_name, product, organism_strain,
    gene_category.
    Verbose adds: matched_terms, gene_summary, function_description.
    """
```

- **Breaking change:** returns `dict` instead of `list[dict]`
- **Breaking change:** adds `summary`, `verbose`, `limit` params
- `summary=True` → `limit=0`
- 2-query pattern: summary always runs, detail skipped when `limit=0`
- Summary query returns single row: `conn.execute_query(...)[0]`
- Rename APOC `{item, count}` to domain keys via `_rename_freq()` helper
  (same pattern as `genes_by_function`), sort desc
- Validation: `term_ids` must be non-empty (raises `ValueError`)
- `ontology` validated by builder (`ValueError`)

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

Pydantic response models:

```python
class GenesByOntologyResult(BaseModel):
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
    gene_name: str | None = Field(default=None, description="Gene name (e.g. 'dnaN')")
    product: str | None = Field(default=None, description="Gene product (e.g. 'DNA polymerase III, beta subunit')")
    organism_strain: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
    gene_category: str | None = Field(default=None, description="Functional category (e.g. 'Replication and repair')")
    # verbose only
    matched_terms: list[str] | None = Field(default=None, description="Input term IDs this gene was matched through (e.g. ['go:0006260'])")
    gene_summary: str | None = Field(default=None, description="Concatenated summary text")
    function_description: str | None = Field(default=None, description="Curated functional description")

class OntologyOrganismBreakdown(BaseModel):
    organism: str = Field(description="Organism strain (e.g. 'Prochlorococcus MED4')")
    count: int = Field(description="Number of matching genes (e.g. 131)")

class OntologyCategoryBreakdown(BaseModel):
    category: str = Field(description="Gene category (e.g. 'Replication and repair')")
    count: int = Field(description="Number of matching genes (e.g. 321)")

class OntologyTermBreakdown(BaseModel):
    term_id: str = Field(description="Input term ID (e.g. 'go:0006260')")
    count: int = Field(description="Genes annotated to this term or descendants (e.g. 411)")

class GenesByOntologyResponse(BaseModel):
    total_matching: int = Field(description="Distinct genes matching (e.g. 1742)")
    by_organism: list[OntologyOrganismBreakdown] = Field(description="Gene counts per organism, sorted desc")
    by_category: list[OntologyCategoryBreakdown] = Field(description="Gene counts per gene_category, sorted desc")
    by_term: list[OntologyTermBreakdown] = Field(description="Gene counts per input term, sorted desc (can overlap)")
    returned: int = Field(description="Results in this response (0 when summary=true)")
    truncated: bool = Field(description="True if total_matching > returned")
    results: list[GenesByOntologyResult] = Field(
        default_factory=list, description="One row per distinct gene",
    )
```

### Wrapper

```python
@mcp.tool(
    tags={"genes", "ontology"},
    annotations={"readOnlyHint": True},
)
async def genes_by_ontology(
    ctx: Context,
    term_ids: Annotated[list[str], Field(
        description="Ontology term IDs (from search_ontology). "
        "E.g. ['go:0006260', 'go:0006412'].",
    )],
    ontology: Annotated[Literal[
        "go_bp", "go_mf", "go_cc", "kegg", "ec",
        "cog_category", "cyanorak_role", "tigr_role", "pfam",
    ], Field(
        description="Ontology the term IDs belong to.",
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
        description="Include matched_terms, gene_summary, function_description.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GenesByOntologyResponse:
    """Find genes annotated to ontology terms, with hierarchy expansion.

    Takes term IDs from search_ontology and finds all genes annotated to
    those terms or any descendant terms in the ontology hierarchy.
    Results are distinct genes (deduplicated across terms).

    For term discovery, use search_ontology first.
    For per-gene ontology details, use gene_ontology_terms.
    """
    await ctx.info(f"genes_by_ontology term_ids={term_ids} ontology={ontology} organism={organism}")
    try:
        conn = _conn(ctx)
        data = api.genes_by_ontology(
            term_ids, ontology, organism=organism,
            summary=summary, verbose=verbose, limit=limit, conn=conn,
        )
        by_organism = [OntologyOrganismBreakdown(**b) for b in data["by_organism"]]
        by_category = [OntologyCategoryBreakdown(**b) for b in data["by_category"]]
        by_term = [OntologyTermBreakdown(**b) for b in data["by_term"]]
        results = [GenesByOntologyResult(**r) for r in data["results"]]
        return GenesByOntologyResponse(
            total_matching=data["total_matching"],
            by_organism=by_organism,
            by_category=by_category,
            by_term=by_term,
            returned=data["returned"],
            truncated=data["truncated"],
            results=results,
        )
    except ValueError as e:
        await ctx.warning(f"genes_by_ontology error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"genes_by_ontology unexpected error: {e}")
        raise ToolError(f"Error in genes_by_ontology: {e}")
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

Replace `TestBuildGenesByOntology` with:

```
class TestBuildGenesByOntology:
    test_returns_expected_columns (parametrize ontologies)
    test_verbose_false (no matched_terms/gene_summary/function_description)
    test_verbose_true (matched_terms, gene_summary, function_description present)
    test_limit_clause
    test_limit_none
    test_organism_filter_clause
    test_order_by_organism_then_locus
    test_hierarchy_expansion (go_bp has hierarchy)
    test_no_hierarchy (cog_category)
    test_kegg_level_filter
    test_pfam_parent_label
    test_invalid_ontology_raises_valueerror

class TestBuildGenesByOntologySummary:
    test_returns_summary_keys (total_matching, by_organism, by_term)
    test_correct_hierarchy_expansion (parametrize)
    test_organism_filter
    test_invalid_ontology_raises_valueerror
    test_pfam_parent_label
```

### Unit: API function (`test_api_functions.py`)

Replace `TestGenesByOntology` with:

```
class TestGenesByOntology:
    test_returns_dict (not list)
    test_summary_sets_limit_zero
    test_passes_params (term_ids, ontology, organism, verbose, limit)
    test_creates_conn_when_none
    test_empty_term_ids_raises
    test_invalid_ontology_raises
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

Replace genes_by_ontology tests with:

```
class TestGenesByOntologyWrapper:
    test_returns_dict_envelope
    test_empty_results
    test_params_forwarded (term_ids, ontology, organism, summary, verbose, limit)
    test_truncation_metadata
    test_invalid_ontology_raises_toolerror
```

Update `EXPECTED_TOOLS` (tool name unchanged).

### Integration (`test_tool_correctness_kg.py`)

Against live KG:
- go_bp search returns expected fields in dict envelope
- Summary mode returns counts only
- Organism filter reduces results
- Each result has expected compact columns

### Regression (`test_regression.py`)

Update `TOOL_BUILDERS` (signature changed: added verbose, limit):
```python
"genes_by_ontology": build_genes_by_ontology,  # signature updated
```

Regenerate baselines: `pytest tests/regression/ --force-regen -m kg`

### Eval cases (`cases.yaml`)

```yaml
- id: genes_by_ontology_go_bp
  tool: genes_by_ontology
  desc: GO biological process term to genes
  params:
    term_ids: ["go:0006260"]
    ontology: go_bp
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain]

- id: genes_by_ontology_kegg
  tool: genes_by_ontology
  desc: KEGG term to genes (with level filter)
  params:
    term_ids: ["kegg:K00001"]
    ontology: kegg
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain]

- id: genes_by_ontology_pfam
  tool: genes_by_ontology
  desc: Pfam domain to genes (parent_label pattern)
  params:
    term_ids: ["PF00001"]
    ontology: pfam
  expect:
    min_rows: 0
    columns: [locus_tag, organism_strain]
```

---

## About Content

### Input YAML

**File:** `multiomics_explorer/inputs/tools/genes_by_ontology.yaml`

```yaml
examples:
  - title: Find genes in a GO biological process
    call: genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp")
    response: |
      {
        "total_matching": 411,
        "by_organism": [{"organism": "Alteromonas macleodii EZ55", "count": 44}, ...],
        "by_term": [{"term_id": "go:0006260", "count": 411}],
        "returned": 5, "truncated": true,
        "results": [
          {"locus_tag": "A9601_00001", "gene_name": "dnaN",
           "product": "DNA polymerase III, beta subunit",
           "organism_strain": "Prochlorococcus AS9601"},
          ...
        ]
      }

  - title: Compare gene counts across terms
    call: genes_by_ontology(term_ids=["go:0006260", "go:0006412"], ontology="go_bp", summary=True)
    response: |
      {
        "total_matching": 1742,
        "by_organism": [{"organism": "Alteromonas macleodii EZ55", "count": 152}, ...],
        "by_term": [{"term_id": "go:0006412", "count": 1331}, {"term_id": "go:0006260", "count": 411}],
        "returned": 0, "truncated": true, "results": []
      }

  - title: Filter by organism
    call: genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp", organism="MED4")

  - title: From term search to gene discovery
    steps: |
      Step 1: search_ontology(search_text="replication", ontology="go_bp")
              → collect term IDs from results (e.g. "go:0006260")

      Step 2: genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp")
              → find genes annotated to these terms (with hierarchy expansion)

      Step 3: gene_overview(locus_tags=["PMM0845", ...])
              → check data availability for discovered genes

verbose_fields:
  - matched_terms
  - gene_summary
  - function_description

chaining:
  - "search_ontology → genes_by_ontology"
  - "genes_by_ontology → gene_overview"
  - "genes_by_ontology → gene_ontology_terms"

mistakes:
  - "term_ids must come from the SAME ontology — don't mix GO and KEGG IDs"
  - "by_term counts can overlap — a gene annotated to 2 input terms is counted in both"
  - "Results are distinct genes, not per-term rows"
  - wrong: "genes_by_ontology(term_ids=['replication'], ontology='go_bp')  # passing text, not IDs"
    right: "search_ontology(search_text='replication', ontology='go_bp')  # search first, then use IDs"
```

### Build

```bash
uv run python scripts/build_about_content.py genes_by_ontology
```

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Documentation

- `CLAUDE.md`: update genes_by_ontology row — mention hierarchy expansion,
  organism grouping, summary fields

## Code Review

Run code-review skill (full checklist) as final step.
