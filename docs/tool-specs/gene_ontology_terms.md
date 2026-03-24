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
| `by_term` | list | Gene counts per term, sorted desc — shows which terms are shared across input genes (e.g. `[{"term_id": "go:0015979", "term_name": "photosynthesis", "ontology_type": "go_bp", "count": 4}, ...]`) |
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

### Architecture: single-ontology vs all-ontology

The builder generates **different Cypher** depending on whether `ontology`
is specified or None:

- **Single ontology** (`ontology="go_bp"`): one focused query using that
  ontology's config from `ONTOLOGY_CONFIG`. Simple, efficient.
- **All ontologies** (`ontology=None`): the **api/ layer orchestrates**
  by calling the single-ontology builder in a loop across all
  `ONTOLOGY_CONFIG` entries and merging results in Python. This avoids
  a massive 9-branch UNION ALL in Cypher (which repeats UNWIND and gene
  lookups 9 times) and keeps each query simple and plan-efficient.

This is a **multi-query orchestration** pattern — the api/ layer runs
up to 9 single-ontology queries (detail) + 9 single-ontology summary
queries and merges. Not_found is computed once with a separate gene
existence check.

### `build_gene_ontology_terms_summary`

```python
def build_gene_ontology_terms_summary(
    *,
    locus_tags: list[str],
    ontology: str,
) -> tuple[str, dict]:
    """Build summary for gene_ontology_terms for ONE ontology.

    RETURN keys: term_count, gene_count, by_term,
    terms_per_gene (list of counts for distribution).

    Called once per ontology by api/ layer (which merges results
    and adds not_found, no_terms, totals).
    """
```

Cypher (single ontology, e.g. go_bp — verified against live KG):
```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})-[:Gene_involved_in_biological_process]->(t:BiologicalProcess)
WHERE NOT EXISTS {
  MATCH (g)-[:Gene_involved_in_biological_process]->(child:BiologicalProcess)
        -[:Biological_process_is_a_biological_process|
           Biological_process_part_of_biological_process]->(t)
}
WITH g.locus_tag AS lt, collect({id: t.id, name: t.name}) AS terms
WITH collect({lt: lt, cnt: size(terms), terms: terms}) AS genes
WITH genes,
     apoc.coll.flatten([g IN genes | g.terms]) AS all_terms,
     [g IN genes | g.cnt] AS terms_per_gene
UNWIND all_terms AS t
WITH genes, terms_per_gene, t.id AS tid, t.name AS tname, count(*) AS cnt
WITH genes, terms_per_gene,
     collect({term_id: tid, term_name: tname, count: cnt}) AS by_term
RETURN size(genes) AS gene_count,
       size(apoc.coll.flatten([g IN genes | g.terms])) AS term_count,
       by_term,
       terms_per_gene
```

Note: `apoc.coll.frequencies()` is NOT used here because it only returns
`{item, count}` on a single field — we need both `term_id` and `term_name`
in `by_term`. Instead, UNWIND + count(*) + collect gives the full breakdown.

The api/ layer:
- Calls this once per ontology (or once if `ontology` specified)
- Merges `by_term` lists across ontologies
- Computes `terms_per_gene_*` distribution from merged per-gene counts
  (using Python `statistics.median`)
- Computes `no_terms` = found locus_tags that appear in zero
  single-ontology results

### Gene existence check (not_found)

Separate lightweight query, called once:
```cypher
UNWIND $locus_tags AS lt
OPTIONAL MATCH (g:Gene {locus_tag: lt})
RETURN lt, g IS NOT NULL AS found
```

Api/ partitions into: found (proceed with ontology queries), not_found
(report in envelope). Consistent with gene_overview pattern but
separated because the ontology queries use MATCH (not OPTIONAL MATCH).

### `build_gene_ontology_terms`

```python
def build_gene_ontology_terms(
    *,
    locus_tags: list[str],
    ontology: str,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_ontology_terms for ONE ontology.

    RETURN keys (compact): locus_tag, term_id, term_name.
    RETURN keys (verbose): adds organism_strain.

    Called by api/ — which adds ontology_type column and merges
    across ontologies when ontology=None.
    """
```

Cypher (single ontology, e.g. go_bp with leaf filter — verified against live KG):
```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})-[:Gene_involved_in_biological_process]->(t:BiologicalProcess)
WHERE NOT EXISTS {
  MATCH (g)-[:Gene_involved_in_biological_process]->(child:BiologicalProcess)
        -[:Biological_process_is_a_biological_process|
           Biological_process_part_of_biological_process]->(t)
}
RETURN g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name
       [, g.organism_strain AS organism_strain]  -- verbose
ORDER BY g.locus_tag, t.id
[LIMIT $limit]
```

For flat/no-op ontologies (cog_category, tigr_role, kegg, pfam):
```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})-[:Gene_in_cog_category]->(t:CogFunctionalCategory)
RETURN g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name
ORDER BY g.locus_tag, t.id
```

### Leaf filtering per ontology

| Ontology | Hierarchy rels | Leaf filter |
|---|---|---|
| go_bp | `is_a`, `part_of` | NOT EXISTS with both rels |
| go_mf | `is_a`, `part_of` | NOT EXISTS with both rels |
| go_cc | `is_a`, `part_of` | NOT EXISTS with both rels |
| ec | `is_a` | NOT EXISTS with single rel |
| kegg | `is_a` | No-op — genes only connect at `ko` level (`gene_connects_to_level`), so no ancestors to filter |
| cog_category | (none) | No-op — flat ontology, no hierarchy |
| cyanorak_role | `is_a` | NOT EXISTS with single rel |
| tigr_role | (none) | No-op — flat ontology, no hierarchy |
| pfam | `Pfam_in_pfam_clan` | No-op — hierarchy goes Pfam→PfamClan, but genes only connect to Pfam nodes (not clans), so no Pfam child can have a clan as ancestor via `Gene_has_pfam` |

**Key insight:** Leaf filtering is only meaningful when a gene can be
annotated to both a child AND its ancestor in the same label. For Pfam,
genes connect to `Pfam` nodes only, and the hierarchy goes to `PfamClan`
(different label) — so the NOT EXISTS pattern from GO/EC wouldn't match
anything. For KEGG, genes connect only at `ko` level. Both are effectively
no-op for leaf filtering.

The builder reads `hierarchy_rels` from ONTOLOGY_CONFIG: if empty or if
the hierarchy crosses labels (`parent_label` present), skip the NOT
EXISTS clause.

**Design notes:**
- Column renamed from `id`/`name` → `term_id`/`term_name` (clearer in batch context)
- `ontology_type` column added by api/ layer when merging across ontologies
  (not in the Cypher — each query is single-ontology)
- Verbose adds `organism_strain` — useful in batch when mixing organisms
- Each builder call is single-ontology — api/ orchestrates the multi-ontology
  case. This keeps Cypher simple and avoids 9x UNWIND repetition.

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

### Orchestration logic

1. **Gene existence check** — one lightweight query to partition
   `locus_tags` into `found` and `not_found`
2. **Determine ontologies** — if `ontology` specified, just that one;
   if None, all 9 from `ONTOLOGY_CONFIG`
3. **Summary queries** — call `build_gene_ontology_terms_summary()` once
   per ontology (only for found genes). Merge results:
   - `by_ontology`: one entry per ontology with `term_count` + `gene_count`
     (skip ontologies with zero terms)
   - `by_term`: merge across ontologies, sort by count desc
   - `terms_per_gene`: merge per-gene counts across ontologies, compute
     min/max/median
   - `no_terms`: found genes that appear in zero ontology results
   - `total_matching`: sum of all term_count
   - `total_genes`: found genes minus no_terms
   - `total_terms`: count of distinct term_ids across all by_term entries
4. **Detail queries** — skip when `limit=0`. Call
   `build_gene_ontology_terms()` once per ontology (for found genes).
   Merge results, add `ontology_type` column when multi-ontology,
   sort by `locus_tag, term_id`, apply limit.

**Performance:** For single-ontology queries, this is 2 Cypher calls
(existence + summary, or existence + detail, or all three). For
all-ontology queries, up to 1 + 9 + 9 = 19 calls in the worst case.
Each call is simple and fast — the KG is local and queries hit indexes.
If performance becomes an issue, can batch ontologies into fewer calls
using CALL subqueries within Cypher.

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
    ontology_type: str = Field(description="Ontology type (e.g. 'go_bp')")
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
          {"term_id": "go:0006260", "term_name": "DNA replication", "ontology_type": "go_bp", "count": 1},
          {"term_id": "go:0006271", "term_name": "DNA strand elongation involved in DNA replication", "ontology_type": "go_bp", "count": 1}
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
