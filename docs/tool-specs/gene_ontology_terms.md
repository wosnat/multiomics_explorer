# Tool spec: gene_ontology_terms

## Purpose

Reverse lookup: given gene locus tags, return the most specific (leaf)
ontology annotations for each gene. Details tool in the ontology triplet
(`search_ontology` → `genes_by_ontology` → `gene_ontology_terms`). Flat
long format — one row per gene × term.

Always returns **leaf terms only** — the most specific terms annotated to
each gene, excluding redundant ancestors implied by the ontology hierarchy.
For hierarchy-aware queries in the other direction (term → genes), use
`genes_by_ontology`. See "Leaf filtering" section below for details.

Existing v1 tool. V3 upgrade: batch input (`locus_tags` list), `not_found`,
summary/verbose/limit controls, dict envelope response, optional ontology
filter (None = all), `leaf_only` parameter removed (always leaf).

## Out of Scope

- **Term search** — use `search_ontology`
- **Term → genes** — use `genes_by_ontology`
- **Gene identity / routing** — use `gene_overview`
- **Full gene properties** — use `run_cypher`

## Status / Prerequisites

- [x] KG spec: not needed — all ontology term properties exist
- [x] Scope reviewed with user
- [x] Result-size controls decided (batch tool: summary + limit)
- [ ] Ready for Phase 2 (build)

## Use cases

- **Gene annotation audit** — "What GO terms is PMM0001 annotated to?"
- **Batch annotation** — given 10 genes from gene_overview, get all their
  ontology annotations in one call
- **Ontology-specific drill-down** — filter to a single ontology (e.g. kegg)
  after seeing annotation_types in gene_overview
- **Chain:** `gene_overview` (check annotation_types) →
  `gene_ontology_terms` (get actual terms) →
  `genes_by_ontology` (find other genes with same terms)

## KG dependencies

- `Gene` nodes: `locus_tag`, `organism_strain`
- Ontology term nodes: `id`, `name` (on all ontology labels:
  BiologicalProcess, MolecularFunction, CellularComponent, EcNumber,
  KeggTerm, CogFunctionalCategory, CyanorakRole, TigrRole, Pfam, PfamClan)
- Gene→Term edges per ontology (from ONTOLOGY_CONFIG)
- Hierarchy edges per ontology (for leaf filtering)

All properties verified present in live KG (2026-03-23).

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes", "ontology"},
    annotations={"readOnlyHint": True},
)
async def gene_ontology_terms(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Gene locus tags to look up. "
        "E.g. ['PMM0001', 'PMM0845'].",
    )],
    ontology: Annotated[
        Literal["go_bp", "go_mf", "go_cc", "kegg", "ec",
                "cog_category", "cyanorak_role", "tigr_role", "pfam"] | None,
        Field(description="Filter to one ontology. None returns all."),
    ] = None,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include organism_strain per row.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GeneOntologyTermsResponse:
    """Get ontology annotations for genes. One row per gene × term.

    Returns the most specific (leaf) terms only — redundant ancestor terms
    are excluded. Use ontology param to filter to one type, or omit for all.

    For the reverse direction (find genes annotated to a term, with hierarchy
    expansion), use genes_by_ontology. Use search_ontology to find terms by text.
    """
```

**Return envelope:** `total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, returned, truncated, not_found, no_terms, results`

**Per-result columns (compact — 3):**
`locus_tag`, `term_id`, `term_name`

**All-ontology mode adds (1):**
`ontology_type` — present when `ontology=None`, absent when filtering to one

**Verbose adds (1):**
`organism_strain`

## Result-size controls

Batch input can be large × multiple ontologies → summary + limit pattern.

### Summary fields (always present)

| Field | Type | Description |
|---|---|---|
| `total_matching` | int | Total gene × term rows matching filters |
| `total_genes` | int | Distinct genes with at least one term (= len(locus_tags) - len(not_found) - len(no_terms)) |
| `total_terms` | int | Distinct terms across all input genes |
| `by_ontology` | list | Per ontology type: term count + gene coverage, sorted by term_count desc (e.g. `[{"ontology_type": "go_bp", "term_count": 12, "gene_count": 8}, ...]`) |
| `by_term` | list | Gene counts per term, sorted desc — shows which terms are shared across input genes (e.g. `[{"term_id": "go:0015979", "term_name": "photosynthesis", "count": 4}, ...]`) |
| `terms_per_gene_min` | int | Fewest leaf terms on any gene with terms (excludes no_terms genes; ≥ 1) |
| `terms_per_gene_max` | int | Most leaf terms on any gene with terms |
| `terms_per_gene_median` | float | Median leaf terms per gene with terms — annotation density signal |

### Batch handling

| Field | Type | Description |
|---|---|---|
| `not_found` | list[str] | Input locus_tags that don't exist in KG |
| `no_terms` | list[str] | Input locus_tags that exist in KG but have no terms (for the queried ontology, or any ontology if ontology=None) |

**Sort key:** `locus_tag ASC, term_id ASC`

**Default limit:** 5 (MCP), None (api/)

**Verbose:**
- Compact: locus_tag, term_id, term_name
- Verbose adds: organism_strain

---

## Special handling

- **2-query pattern:** summary query always runs (OPTIONAL MATCH for
  not_found/no_terms + aggregations), detail query skipped when `limit=0`
- **Multi-ontology UNION:** when `ontology=None`, builder generates a
  UNION ALL across all 9 ONTOLOGY_CONFIG entries. Single-ontology queries
  use a simpler focused query.
- **Conditional `ontology_type` column:** present in results when
  `ontology=None` (all-ontology mode), absent when a specific ontology
  is requested (redundant — caller already knows which ontology).
- **No Lucene:** no fulltext search
- **No caching:** result depends on input locus_tags
- **Validation:** `locus_tags` must be non-empty; `ontology` (when given)
  must be a valid ONTOLOGY_CONFIG key (ValueError otherwise)

---

## Leaf filtering

**What it does:** For hierarchical ontologies (GO, EC, KEGG, CyanorakRole,
TigrRole), genes are often annotated to multiple terms at different
levels of the hierarchy. For example, a gene annotated to
`DNA strand elongation involved in DNA replication` (child) is also
annotated to `DNA replication` (parent) via the `is_a` relationship.
Leaf filtering removes these redundant ancestor terms, returning only
the most specific terms — those with no more-specific child also
annotated to the same gene.

**Why it's always on:** The ancestor terms are implied by the more
specific ones and add noise to results. A gene with 2 meaningful
GO BP annotations might return 15+ rows without filtering, most of
them generic ancestors like `biological_process` or `metabolic process`.

**How it works in Cypher:**
```cypher
MATCH (g:Gene {locus_tag: $lt})-[:Gene_involved_in_biological_process]->(t:BiologicalProcess)
WHERE NOT EXISTS {
  MATCH (g)-[:Gene_involved_in_biological_process]->(child:BiologicalProcess)
        -[:Biological_process_is_a_biological_process|
           Biological_process_part_of_biological_process]->(t)
}
```
"Return term `t` only if no other term the gene is annotated to is a
child of `t` in the hierarchy."

**Flat ontologies:** For `cog_category` (no hierarchy relationships),
no filtering is needed — there are no ancestors to exclude. The builder
skips the NOT EXISTS clause for these.

**Hierarchy in the other direction:** If you need to ask "is this gene
connected to a branch of the ontology?" — that's what `genes_by_ontology`
does. It takes a term ID and expands **down** the hierarchy to find all
genes. The two tools complement each other:

| Direction | Tool | What it does |
|---|---|---|
| gene → terms | `gene_ontology_terms` | Returns leaf terms (most specific) |
| term → genes | `genes_by_ontology` | Expands down hierarchy, finds all genes |

**v1 had a `leaf_only` parameter** (default True). Removed in v3 because:
1. The non-leaf case was rarely useful and flooded results
2. `genes_by_ontology` already handles hierarchy queries from the term side
3. Fewer parameters = cleaner tool surface for the LLM
4. `run_cypher` covers edge cases that need all annotations

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_gene_ontology_terms_summary()` (new) + `build_gene_ontology_terms()` (rewrite) |
| 2 | API function | `api/functions.py` | `gene_ontology_terms()` (rewrite: `list[dict]` → `dict` envelope) |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Verify existing exports (no change expected) |
| 4 | MCP wrapper | `mcp_server/tools.py` | Rewrite: `async def`, Pydantic models, `ToolError` |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | Replace `TestBuildGeneOntologyTerms` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | Replace `TestGeneOntologyTerms` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | Replace `TestGeneOntologyTermsWrapper` |
| 8 | Integration | `tests/integration/test_api_contract.py` | Update `TestGeneOntologyTermsContract` |
| 9 | Regression | `tests/regression/test_regression.py` | Update `TOOL_BUILDERS` |
| 9b | Evals | `tests/evals/test_eval.py` | Update `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | Update params + shape |
| 11 | About content | `multiomics_explorer/inputs/tools/gene_ontology_terms.yaml` | Input YAML → build → verify |
| 12 | Docs | `CLAUDE.md` | Update tool description |
| 13 | Code review | — | Run code-review skill (full checklist) |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_gene_ontology_terms_summary`

```python
def build_gene_ontology_terms_summary(
    *,
    locus_tags: list[str],
    ontology: str | None = None,
) -> tuple[str, dict]:
    """Build summary + not_found for gene_ontology_terms.

    RETURN keys: total_matching, total_genes, total_terms,
    by_ontology, by_term, terms_per_gene_min, terms_per_gene_max,
    terms_per_gene_median, not_found, no_terms.
    """
```

When `ontology` is None, iterate all ONTOLOGY_CONFIG entries. When specified,
use only that one. Each ontology contributes rows tagged with ontology type.

Cypher strategy — UNION across ontologies:
```cypher
UNWIND $locus_tags AS lt
OPTIONAL MATCH (g:Gene {locus_tag: lt})
WITH collect(lt) AS all_tags,
     collect(g) AS genes,
     collect(CASE WHEN g IS NULL THEN lt END) AS not_found_raw
WITH [x IN not_found_raw WHERE x IS NOT NULL] AS not_found,
     [g IN genes WHERE g IS NOT NULL] AS found
// For each found gene × ontology, count term matches
// ... (per-ontology CALL blocks)
RETURN total_matching, total_genes, total_terms,
       by_ontology, by_term,
       terms_per_gene_min, terms_per_gene_max, terms_per_gene_median,
       not_found, no_terms
```

Since each ontology uses a different relationship type and label, the builder
generates per-ontology subqueries (CALL blocks) and aggregates counts.

**Design decision:** Rather than one massive UNION query across all 9 ontologies,
use APOC or multiple CALL subqueries. For single-ontology queries, generate
a simple focused query (same pattern as current v1 but batched).

### `build_gene_ontology_terms`

```python
def build_gene_ontology_terms(
    *,
    locus_tags: list[str],
    ontology: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_ontology_terms.

    RETURN keys (compact): locus_tag, term_id, term_name.
    RETURN keys (all-ontology mode): adds ontology_type.
    RETURN keys (verbose): adds organism_strain.
    """
```

When `ontology` is specified — single-ontology query (simpler):
```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})-[:Gene_involved_in_biological_process]->(t:BiologicalProcess)
WHERE NOT EXISTS { ... }  -- leaf filter (always applied for hierarchical ontologies)
RETURN g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name
       [, g.organism_strain AS organism_strain]  -- verbose
ORDER BY g.locus_tag, t.id
[LIMIT $limit]
```

When `ontology` is None — UNION across all ontologies, each adding a literal
`ontology_type` column:
```cypher
CALL {
  UNWIND $locus_tags AS lt
  MATCH (g:Gene {locus_tag: lt})-[:Gene_involved_in_biological_process]->(t:BiologicalProcess)
  WHERE NOT EXISTS { ... }  -- leaf filter
  RETURN g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name,
         'go_bp' AS ontology_type
         [, g.organism_strain AS organism_strain]
  UNION ALL
  ...  -- repeat for each ontology
}
RETURN locus_tag, term_id, term_name, ontology_type
       [, organism_strain]
ORDER BY locus_tag, term_id
[LIMIT $limit]
```

**Design notes:**
- Column renamed from `id`/`name` → `term_id`/`term_name` (clearer in batch context)
- `ontology_type` column added when querying all ontologies (absent when single)
- Leaf filtering always applied — NOT EXISTS subquery excludes ancestor terms
  (no-op for flat ontologies like cog_category that have no hierarchy)
- Verbose adds `organism_strain` — useful in batch when mixing organisms

---

## API Function

**File:** `api/functions.py`

```python
def gene_ontology_terms(
    locus_tags: list[str],
    ontology: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get ontology annotations for genes.

    Returns dict with keys: total_matching, total_genes, total_terms,
    by_ontology, by_term, terms_per_gene_min, terms_per_gene_max,
    terms_per_gene_median, returned, truncated, not_found, no_terms,
    results.
    Per result: locus_tag, term_id, term_name.
    Verbose adds: organism_strain.
    All-ontology queries add: ontology_type.
    """
```

- **Breaking change:** returns `dict` instead of `list[dict]`
- **Breaking change:** param renamed from `gene_id` to `locus_tags` (list)
- **Breaking change:** `ontology` now optional (None = all ontologies)
- `summary=True` → `limit=0`
- Always run summary query → all summary fields + not_found + no_terms
- Skip detail when `limit=0`
- Rename APOC `{item, count}` to domain keys via `_rename_freq()` helper

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

Pydantic response models:

```python
class OntologyTermRow(BaseModel):
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
    term_id: str = Field(description="Ontology term ID (e.g. 'go:0006260')")
    term_name: str = Field(description="Term name (e.g. 'DNA replication')")
    ontology_type: str | None = Field(default=None, description="Ontology type when querying all (e.g. 'go_bp')")
    # verbose-only
    organism_strain: str | None = Field(default=None, description="Organism (e.g. 'Prochlorococcus MED4')")

class OntologyTypeBreakdown(BaseModel):
    ontology_type: str = Field(description="Ontology type (e.g. 'go_bp', 'kegg')")
    term_count: int = Field(description="Total leaf terms in this ontology (e.g. 12)")
    gene_count: int = Field(description="Input genes with at least one term in this ontology (e.g. 8)")

class TermBreakdown(BaseModel):
    term_id: str = Field(description="Ontology term ID (e.g. 'go:0015979')")
    term_name: str = Field(description="Term name (e.g. 'photosynthesis')")
    count: int = Field(description="Genes annotated to this term (e.g. 4)")

class GeneOntologyTermsResponse(BaseModel):
    total_matching: int = Field(description="Total gene × term annotation rows")
    total_genes: int = Field(description="Distinct genes with at least one term")
    total_terms: int = Field(description="Distinct terms across all input genes")
    by_ontology: list[OntologyTypeBreakdown] = Field(description="Per ontology type: term + gene counts, sorted by term_count desc")
    by_term: list[TermBreakdown] = Field(description="Gene counts per term, sorted desc — shows shared terms across input genes")
    terms_per_gene_min: int = Field(description="Fewest leaf terms on any gene with terms (e.g. 1)")
    terms_per_gene_max: int = Field(description="Most leaf terms on any gene with terms (e.g. 15)")
    terms_per_gene_median: float = Field(description="Median leaf terms per gene with terms (e.g. 6.0)")
    returned: int = Field(description="Results in this response (0 when summary=true)")
    truncated: bool = Field(description="True if total_matching > returned")
    not_found: list[str] = Field(default_factory=list, description="Input locus_tags not in KG")
    no_terms: list[str] = Field(default_factory=list, description="Input locus_tags in KG but with no terms for queried ontology")
    results: list[OntologyTermRow] = Field(default_factory=list, description="One row per gene × term")
```

### Wrapper

```python
@mcp.tool(
    tags={"genes", "ontology"},
    annotations={"readOnlyHint": True},
)
async def gene_ontology_terms(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Gene locus tags to look up. "
        "E.g. ['PMM0001', 'PMM0845'].",
    )],
    ontology: Annotated[
        Literal["go_bp", "go_mf", "go_cc", "kegg", "ec",
                "cog_category", "cyanorak_role", "tigr_role", "pfam"] | None,
        Field(description="Filter to one ontology. None returns all."),
    ] = None,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include organism_strain per row.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GeneOntologyTermsResponse:
    """Get ontology annotations for genes. One row per gene × term.

    Returns the most specific (leaf) terms only — redundant ancestor terms
    are excluded. Use ontology param to filter to one type, or omit for all.

    For the reverse direction (find genes annotated to a term, with hierarchy
    expansion), use genes_by_ontology. Use search_ontology to find terms by text.
    """
    await ctx.info(f"gene_ontology_terms locus_tags={locus_tags} ontology={ontology}")
    try:
        conn = _conn(ctx)
        data = api.gene_ontology_terms(
            locus_tags, ontology=ontology,
            summary=summary, verbose=verbose, limit=limit, conn=conn,
        )
        results = [OntologyTermRow(**r) for r in data["results"]]
        by_ontology = [OntologyTypeBreakdown(**b) for b in data["by_ontology"]]
        by_term = [TermBreakdown(**b) for b in data["by_term"]]
        return GeneOntologyTermsResponse(
            **{**data, "results": results, "by_ontology": by_ontology, "by_term": by_term},
        )
    except ValueError as e:
        await ctx.warning(f"gene_ontology_terms error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"gene_ontology_terms unexpected error: {e}")
        raise ToolError(f"Error in gene_ontology_terms: {e}")
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

Replace `TestBuildGeneOntologyTerms` with:

```
class TestBuildGeneOntologyTerms:
    test_single_ontology_returns_expected_columns
    test_all_ontologies_returns_union (ontology=None)
    test_leaf_filter_hierarchical (NOT EXISTS clause for GO/EC/KEGG)
    test_leaf_filter_flat_ontology (cog_category — no hierarchy, no NOT EXISTS)
    test_verbose_false (no organism_strain)
    test_verbose_true (organism_strain present)
    test_limit_clause
    test_limit_none
    test_order_by (locus_tag, term_id)
    test_invalid_ontology_raises

class TestBuildGeneOntologyTermsSummary:
    test_returns_summary_keys
    test_not_found_logic (OPTIONAL MATCH)
    test_single_ontology
    test_all_ontologies
```

### Unit: API function (`test_api_functions.py`)

Replace `TestGeneOntologyTerms` with:

```
class TestGeneOntologyTerms:
    test_returns_dict (not list)
    test_summary_sets_limit_zero
    test_passes_params (locus_tags, ontology, verbose, limit)
    test_creates_conn_when_none
    test_not_found_populated
    test_ontology_none_queries_all
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

Replace `TestGeneOntologyTermsWrapper` with:

```
class TestGeneOntologyTermsWrapper:
    test_returns_dict_envelope
    test_empty_results (not_found populated)
    test_params_forwarded (locus_tags, ontology, summary, verbose, limit)
    test_truncation_metadata
    test_invalid_ontology_raises_tool_error
```

Update `EXPECTED_TOOLS` (tool name unchanged).

### Integration (`test_api_contract.py`)

Update `TestGeneOntologyTermsContract`:
- Batch query returns expected fields in dict envelope
- Not-found gene returns `not_found` populated
- Each result has expected compact columns (locus_tag, term_id, term_name)
- Single-ontology filter works
- All-ontology query includes ontology_type column

### Regression (`test_regression.py`)

Update `TOOL_BUILDERS` (builder signature changed: `gene_id` → `locus_tags`):
```python
"gene_ontology_terms": build_gene_ontology_terms,
```

### Eval cases (`cases.yaml`)

```yaml
- id: gene_ontology_terms_bp_leaf
  tool: gene_ontology_terms
  desc: GO biological process leaf terms for a gene
  params:
    locus_tags: ["PMM0001"]
    ontology: go_bp
  expect:
    min_rows: 1
    columns: [locus_tag, term_id, term_name]

- id: gene_ontology_terms_all_ontologies
  tool: gene_ontology_terms
  desc: All ontology terms for a well-annotated gene
  params:
    locus_tags: ["PMM0001"]
  expect:
    min_rows: 1
    columns: [locus_tag, term_id, term_name, ontology_type]

- id: gene_ontology_terms_batch
  tool: gene_ontology_terms
  desc: Batch ontology terms for Pro + Alt genes
  params:
    locus_tags: ["PMM0001", "EZ55_00275"]
    ontology: go_bp
  expect:
    min_rows: 1
    columns: [locus_tag, term_id, term_name]

- id: gene_ontology_terms_kegg
  tool: gene_ontology_terms
  desc: KEGG terms for a gene
  params:
    locus_tags: ["PMM0001"]
    ontology: kegg
  expect:
    min_rows: 1
    columns: [locus_tag, term_id, term_name]
```

Regenerate regression baselines: `pytest tests/regression/ --force-regen -m kg`

---

## About Content

### Input YAML

**File:** `multiomics_explorer/inputs/tools/gene_ontology_terms.yaml`

```yaml
examples:
  - title: GO biological process terms for a gene
    call: gene_ontology_terms(locus_tags=["PMM0001"], ontology="go_bp")
    response: |
      {
        "total_matching": 2, "total_genes": 1, "total_terms": 2,
        "by_ontology": [{"ontology_type": "go_bp", "term_count": 2, "gene_count": 1}],
        "by_term": [
          {"term_id": "go:0006260", "term_name": "DNA replication", "count": 1},
          {"term_id": "go:0006271", "term_name": "DNA strand elongation involved in DNA replication", "count": 1}
        ],
        "terms_per_gene_min": 2, "terms_per_gene_max": 2, "terms_per_gene_median": 2.0,
        "returned": 2, "truncated": false, "not_found": [], "no_terms": [],
        "results": [
          {"locus_tag": "PMM0001", "term_id": "go:0006260", "term_name": "DNA replication"},
          {"locus_tag": "PMM0001", "term_id": "go:0006271", "term_name": "DNA strand elongation involved in DNA replication"}
        ]
      }

  - title: All ontology annotations for a gene
    call: gene_ontology_terms(locus_tags=["PMM0001"])

  - title: Batch annotations with summary only
    call: gene_ontology_terms(locus_tags=["PMM0001", "PMM0845", "EZ55_00275"], summary=True)

  - title: From overview to ontology details
    steps: |
      Step 1: gene_overview(locus_tags=["PMM0001"])
              → check annotation_types: ["go_bp", "go_mf", "kegg", "ec", ...]

      Step 2: gene_ontology_terms(locus_tags=["PMM0001"], ontology="go_bp")
              → get actual GO BP terms

      Step 3: genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp")
              → find other genes with same term

verbose_fields:
  - organism_strain

chaining:
  - "gene_overview → gene_ontology_terms (check annotation_types first)"
  - "gene_ontology_terms → genes_by_ontology (reverse: term → other genes)"
  - "resolve_gene → gene_ontology_terms"

mistakes:
  - "ontology=None returns ALL ontology types — use ontology filter when you only need one type"
  - "returns only leaf (most specific) terms — ancestor terms like 'metabolic process' are excluded because they are implied by the more specific child terms"
  - "to check if a gene is connected to a broad term (e.g. 'DNA repair'), use genes_by_ontology which expands down the hierarchy — gene_ontology_terms only returns the leaf annotations"
```

### Build

```bash
uv run python scripts/build_about_content.py gene_ontology_terms
```

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Documentation

- `CLAUDE.md`: update `gene_ontology_terms` description to mention batch,
  summary fields, leaf terms, optional ontology filter

## Code Review

Run code-review skill (full checklist) as final step.
