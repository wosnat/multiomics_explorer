# `genes_by_ontology` Redefinition Design Spec

**Status:** Draft (updated 2026-04-14 after KG rebuild + ontology_landscape landing)
**Date:** 2026-04-12 (revised 2026-04-14)
**Parent spec:** [2026-04-12-kg-enrichment-surface-design.md](2026-04-12-kg-enrichment-surface-design.md)
**Depends on:** unified `level:int` property on ontology-term nodes — landed 2026-04-13 (see KG change doc `ontology-level.md`).
**Scope:** Child 2 of the KG enrichment surface work. **Breaking change** to an existing MCP tool.

## What's in this spec

Redefine the existing `genes_by_ontology` tool:

- Change output shape from distinct-gene rows to `(gene × term)` long format (TERM2GENE model).
- Add `level` as an input; either `level` or `term_ids` (or both) must be supplied.
- Make `organism` required and single-valued — matches `ontology_landscape`, `differential_expression_by_gene`, and `pathway_enrichment` (Child 3).
- Add `min_gene_set_size` / `max_gene_set_size` params with the same defaults (5, 500) as landscape and enrichment.
- Use the new `level:int` property directly; drop the pre-rebuild `descendant.level = '<string>'` filter and the `*0..15` depth bound.
- Surface four validation buckets (`not_found`, `wrong_ontology`, `wrong_level`, `filtered_out`) so silent misrouting becomes visible.

As part of this work, **extract a shared hierarchy helper** in `kg/queries_lib.py` and refactor `build_ontology_landscape` onto it — one source of truth before `pathway_enrichment` arrives.

## Rationale

The current tool returns distinct genes with term attribution hidden inside a verbose `matched_terms` list. That shape:

- Is awkward for enrichment: pathway definitions need `(gene, term)` pairs directly (the TERM2GENE model clusterProfiler uses).
- Loses information the new shape exposes — which term(s) each gene matched on.
- Forces any roll-up-to-level use case into 69+ separate calls (B1's original workaround).

Adding a second tool (`genes_by_ontology_level`) with similar output shape creates two near-duplicate tools. Redefining in place is cleaner:
- One tool, one mental model: "find `(gene, term)` pairs for this ontology, scoped by input terms and/or a target level."
- Fits the `genes_by_*` family pattern — long-format rows with shared envelope conventions.

## Signature

```python
genes_by_ontology(
    ontology: str,                   # one of ALL_ONTOLOGIES
    organism: str,                   # required, single-valued
    level: int | None = None,
    term_ids: list[str] | None = None,
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,        # MCP default 500
    offset: int = 0,
)
```

**Input validation (L2, raises `ValueError`):**
- At least one of `level` or `term_ids` must be provided.
- `ontology` must be in `ALL_ONTOLOGIES`.
- `min_gene_set_size >= 0`, `max_gene_set_size >= min_gene_set_size`.

## Three modes, unified output shape

1. **`term_ids` only** — "gene discovery by pathway/term."
   - Expand DOWN from each input term: `(root)<-[:hierarchy*0..]-(leaf)<-[:gene_rel]-(g)`.
   - Row `term_id` = the input term the gene matched against.
   - Size filter applied to each input term's expanded distinct-gene count (organism-scoped).

2. **`level` only** — "pathway definitions at level N."
   - Roll UP from every gene in the ontology: `(g)-[:gene_rel]->(leaf)-[:hierarchy*0..]->(ancestor)` with `ancestor.level = $level`.
   - Row `term_id` = the level-N ancestor term.
   - Primary consumer of Child 3's `pathway_enrichment` for inspecting pathway definitions.

3. **`level` AND `term_ids`** — "scope rollup to specific pathways."
   - `term_ids` validated: must be in `ontology` AND at `level`. Violators go to `wrong_ontology` or `wrong_level`.
   - Row `term_id` = one of the supplied level-N terms.

**KEGG note:** gene→KEGG edges only terminate at the KO leaf (`level_kind='ko'`, `level=3`). Walks up via `Kegg_term_is_a_kegg_term` to any higher level. The legacy `gene_connects_to_level='ko'` string-compare in ONTOLOGY_CONFIG is obsolete — the graph structure enforces this naturally. Removed as part of this work.

**Pfam note:** Pfam is a true 2-level ontology — level 0 = PfamClan, level 1 = Pfam (domains). The KG already carries `PfamClan.level=0` and `Pfam.level=1`. Gene→Pfam edges terminate at the leaf (`Gene_has_pfam`); walks UP via `Pfam_in_pfam_clan` reach the clan parent. Both Pfam and PfamClan term IDs are valid input for `ontology='pfam'`. This diverges from `ontology_landscape`, which currently treats Pfam as flat (hardcodes Pfam level-1 only); landscape's refactor onto the shared helper picks up the 2-level treatment as a side benefit.

**GO-DAG caveat:** because GO's `level` is min-path from root, ~15% of `is_a` edges violate `child.level > parent.level` (child can reach root via a shorter alternate parent). Walking `(leaf)-[:is_a*0..]->(t) WHERE t.level = $level` still yields correct results because the filter is on `t`'s min-level property, not on the walk path.

## Row shape

**Compact (always returned):**

```python
class GenesByOntologyResult(BaseModel):
    locus_tag: str
    gene_name: str | None = None
    product: str | None = None
    gene_category: str | None = None
    term_id: str
    term_name: str
    level: int
    # verbose-only
    function_description: str | None = None
    level_is_best_effort: bool | None = None   # sparse, GO-only, set only when True
```

**Notes:**
- `organism_name` hoisted to envelope (single-organism enforced).
- `matched_terms` dropped — value is debug-only, `gene_ontology_terms` gives gene→leaf mapping.
- `gene_summary` dropped from verbose — long-format rows multiply payload (gene × 20 ancestors = 20× summary text). Callers wanting narrative chain to `gene_overview`.
- `function_description` kept in verbose — short enough that duplication is tolerable.
- `level` in compact — per-row useful in Mode 1 (input terms may span levels); costs one int.
- `level_is_best_effort` sparse + verbose-only — Pydantic `bool | None = None`; absent when not GO or not best-effort. DataFrame users must `.fillna(False)` before boolean filtering (column becomes object dtype).

## Response envelope

Per layer-rules: L2 returns the complete dict; L3 wraps with Pydantic.

```python
class GenesByOntologyResponse(BaseModel):
    # Echo
    ontology: str
    organism_name: str

    # Counts (matches gene_ontology_terms / genes_by_homolog_group conventions)
    total_matching: int              # (gene × term) row count
    total_genes: int                 # distinct genes (recovers old tool's "total_matching" meaning)
    total_terms: int                 # distinct terms emitted
    total_categories: int            # distinct gene_category values

    # Distributions (both min/median/max, matches gene_ontology_terms)
    genes_per_term_min: int
    genes_per_term_median: float
    genes_per_term_max: int
    terms_per_gene_min: int
    terms_per_gene_median: float
    terms_per_gene_max: int

    # Breakdowns (by_X = bounded full list; top_X = unbounded top-5)
    by_category: list[CategoryBreakdown]     # full list (~15-30 cats)
    by_level: list[LevelBreakdown]           # sorted by level asc
    top_terms: list[TermBreakdown]           # top 5 by row count, tie-break term_id

    # GO-specific
    n_best_effort_terms: int         # distinct best-effort terms in the result set (0 for non-GO)

    # Validation (flat lists, one per reason — matches family pattern)
    not_found: list[str]             # term_ids absent from KG entirely
    wrong_ontology: list[str]        # term_ids present in KG under a different ontology label
    wrong_level: list[str]           # term_ids at the right ontology but wrong level (Mode 3 only)
    filtered_out: list[str]          # term_ids valid but gene-set size outside [min, max]

    # Pagination
    returned: int
    offset: int = 0
    truncated: bool
    results: list[GenesByOntologyResult] = []


class CategoryBreakdown(BaseModel):
    category: str
    count: int

class LevelBreakdown(BaseModel):
    level: int
    n_terms: int       # distinct terms at this level in the result
    n_genes: int       # distinct genes reached via this level (set-union across terms)
    row_count: int     # (gene × term) rows at this level

class TermBreakdown(BaseModel):
    term_id: str
    term_name: str
    count: int         # gene count for this term
```

**Deliberately not included:**
- `by_organism` — degenerate for single-organism (matches `differential_expression_by_gene`).
- `score_max` / `score_median` — no Lucene search here.
- `annotation_quality` — not in current tool; backlog if enrichment QC needs it.
- `ontology_type` per row — tool requires one ontology.

## Query architecture (verified against live KG 2026-04-14)

Three Cypher queries + one Python composer. Each query single-purpose, independently testable.

### Shared hierarchy helper

`_hierarchy_walk(ontology: str, direction: Literal["up", "down"]) -> dict` in `kg/queries_lib.py`. Returns Cypher fragments for bind + walk.

Dispatches on ONTOLOGY_CONFIG:
- **Single-label tree ontologies** (GO BP/MF/CC, EC, KEGG, CyanoRak): walk via `[:{rel_union}*0..]` where `rel_union = '|'.join(cfg["hierarchy_rels"])`. `t` and `leaf` share the same label.
- **Cross-label tree ontology (`pfam`):** 2 levels — level 1 = `Pfam` leaf, level 0 = `PfamClan` parent, connected by `Pfam_in_pfam_clan` (child → parent). Helper emits label-aware bind + walk clauses:
  - Direction `up` (Mode 2/3 UP from leaf to ancestor): `MATCH (g:Gene)-[:Gene_has_pfam]->(leaf:Pfam) MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t) WHERE t:Pfam OR t:PfamClan`.
  - Direction `down` (Mode 1 DOWN from root): handles either a Pfam root (no walk, `t = leaf`) or a PfamClan root (walk `(t:PfamClan)<-[:Pfam_in_pfam_clan]-(leaf:Pfam)`). The dispatch reads the input term's label at runtime via a `FOREACH`/`CALL` branch, or the composer passes the label alongside the ID from Query V.
- **Flat ontologies** (`cog_category`, `tigr_role`): no walk; `t = leaf`.

`build_ontology_landscape` refactors onto this helper in the same PR — and as a side effect picks up 2-level Pfam treatment (currently hardcoded as flat level=1 only).

### Query D — detail rows (per mode)

**Mode 1** (term_ids, expand DOWN):
```cypher
UNWIND $term_ids AS input_tid
MATCH (t:{label} {id: input_tid})
MATCH (t)<-[:{rel_union}*0..]-(leaf:{label})
MATCH (g:Gene {organism_name: $org})-[:{gene_rel}]->(leaf)
WITH t, collect(DISTINCT g) AS term_genes
WHERE size(term_genes) >= $min_gene_set_size
  AND size(term_genes) <= $max_gene_set_size
UNWIND term_genes AS g
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.gene_category AS gene_category,
       t.id AS term_id, t.name AS term_name, t.level AS level
       [, g.function_description AS function_description,
          t.level_is_best_effort IS NOT NULL AS level_is_best_effort]  -- verbose
ORDER BY t.id, g.locus_tag
SKIP $offset LIMIT $limit
```

**Mode 2** (level, roll UP):
```cypher
MATCH (g:Gene {organism_name: $org})-[:{gene_rel}]->(leaf:{label})
MATCH (leaf)-[:{rel_union}*0..]->(t:{label})
WHERE t.level = $level
WITH t, collect(DISTINCT g) AS term_genes
WHERE size(term_genes) >= $min_gene_set_size
  AND size(term_genes) <= $max_gene_set_size
UNWIND term_genes AS g
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.gene_category AS gene_category,
       t.id AS term_id, t.name AS term_name, t.level AS level
       [verbose additions as above]
ORDER BY t.id, g.locus_tag
SKIP $offset LIMIT $limit
```

**Mode 3** (level + term_ids): Mode 2 with extra predicate `AND t.id IN $term_ids`.

Verified on live KG:
- Mode 2 `go_bp, level=1, MED4, [5,500]` → 410 rows, 332 genes, 8 terms.
- Mode 1 mixed-level `[cellular process L1, DNA replication L6]` with max=2000 → 1068 rows, `by_level={1: 1038, 6: 30}`, 30 genes hit both levels. Math: 1038 + 30 = 1068 ✓.

### Query A — per-term aggregate

Same MATCH/filter stage; different terminal aggregation.

```cypher
# ... mode-specific MATCH + size filter ...
UNWIND term_genes AS g
WITH t, collect({lt: g.locus_tag, cat: coalesce(g.gene_category, 'Unknown')}) AS gene_rows
RETURN t.id AS term_id, t.name AS term_name, t.level AS level,
       t.level_is_best_effort IS NOT NULL AS best_effort,
       size(gene_rows) AS n_genes,
       apoc.coll.frequencies([r IN gene_rows | r.cat]) AS cat_freqs
ORDER BY t.id
```

**Feeds:** `top_terms` (sort desc by `n_genes`, head 5), `by_level` (`n_terms`, `row_count`), `n_best_effort_terms`, `filtered_out` detection (Modes 1 and 3 — input `term_ids` that passed validation but aren't in Query A's output; Mode 2 leaves `filtered_out=[]`).

### Query B — per-gene aggregate

Same MATCH/filter stage; aggregate over genes.

```cypher
# ... mode-specific MATCH + size filter ...
UNWIND term_genes AS g
WITH g, collect(DISTINCT t.id) AS gene_terms, collect(DISTINCT t.level) AS gene_levels
RETURN g.locus_tag AS locus_tag,
       coalesce(g.gene_category, 'Unknown') AS gene_category,
       size(gene_terms) AS n_terms,
       gene_levels AS levels_hit
ORDER BY g.locus_tag
```

**Feeds:** `total_genes` (`len(per_gene)`), `total_categories` (distinct gene_category), `by_category` (counter over `gene_category`), `terms_per_gene_*` (stats over `n_terms`), `by_level.n_genes` (for each level L: count of genes with `L in levels_hit`).

### Query V — term validation (when `term_ids` is set)

```cypher
UNWIND $term_ids AS tid
OPTIONAL MATCH (t {id: tid})
  WHERE t:BiologicalProcess OR t:MolecularFunction OR t:CellularComponent
     OR t:EcNumber OR t:KeggTerm OR t:CogFunctionalCategory
     OR t:CyanorakRole OR t:TigrRole OR t:Pfam OR t:PfamClan
WITH tid, head(collect(t)) AS t
RETURN tid,
  CASE
    WHEN t IS NULL THEN 'not_found'
    WHEN NOT ANY(L IN $expected_labels WHERE L IN labels(t)) THEN 'wrong_ontology'
    WHEN $level IS NOT NULL AND t.level <> $level THEN 'wrong_level'
    ELSE 'ok'
  END AS status,
  CASE WHEN t IS NOT NULL THEN [L IN labels(t) WHERE L IN $expected_labels][0] END AS matched_label
```

`$expected_labels`: singleton for single-label ontologies (`['KeggTerm']`, `['BiologicalProcess']`, …). For `ontology='pfam'`: `['Pfam', 'PfamClan']`. `matched_label` feeds back to the composer so Mode 1 can dispatch between the "no walk" (Pfam root) and "walk down" (PfamClan root) branches.

Verified on live KG — all four statuses classified correctly for a mixed input.

### Python composer (`api/functions.py`)

Runs Query V (if `term_ids`) → Query A → Query B → composes envelope. Query D runs unless `summary=True`. Total: 3–4 Cypher calls per invocation.

Cross-validates `total_matching == sum(per_term.n_genes) == count(per_gene × avg(n_terms))`; mismatch indicates a Cypher bug.

## Default `limit`

- api/ default: `None` (all rows).
- MCP default: **500**. Larger than other tools' default (5) because this tool's primary consumer is enrichment — pathway definitions need to see a representative slice. Regression baselines will capture a 500-row snapshot so changes surface clearly.

## Layer-rules compliance

- **L1:** `build_genes_by_ontology_detail`, `build_genes_by_ontology_per_term`, `build_genes_by_ontology_per_gene`, `build_genes_by_ontology_validate` in `kg/queries_lib.py`. Each returns `(cypher, params)`. Shared helper `_hierarchy_walk` (internal, not exported).
- **L2:** `genes_by_ontology()` in `api/functions.py` returns full response dict. Validates inputs (raises `ValueError`). Orchestrates Query V → A → B → D → composer.
- **L3:** thin MCP wrapper in `mcp_server/tools.py`. Pydantic response model. Default `limit=500`. Uses `ToolError` for invalid input. `await ctx.info` for per-call logging; `ctx.warning` when `wrong_*` buckets non-empty.
- **L4:** `inputs/tools/genes_by_ontology.yaml` rewritten; skill reference auto-regenerated via `scripts/build_about_content.py` + `scripts/sync_skills.sh`.

## YAML about-content

**Rewrite** `inputs/tools/genes_by_ontology.yaml`:

**Examples:**
- Mode 1: `genes_by_ontology(ontology="go_bp", organism="MED4", term_ids=["go:0006260"])` — gene discovery (long-format response).
- Mode 2: `genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)` — full pathway definitions at level 1 (replaces B1's 69-call workaround).
- Mode 3: `genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1, term_ids=["cyanorak.role:J", "cyanorak.role:K"])` — scoped rollup.
- `summary=True` variant for breakdown-only output.
- `min_gene_set_size=0, max_gene_set_size=null` — inspect all pathways regardless of size.

**Chaining:**
- `ontology_landscape → genes_by_ontology(level=N)` — pick level → inspect pathway defs.
- `search_ontology → genes_by_ontology(term_ids=[...])` — term discovery → gene membership.
- `genes_by_ontology → pathway_enrichment` — pathway defs → enrichment.
- `genes_by_ontology → gene_overview` — explore specific genes after filtering.

**Verbose fields:** `function_description`, `level_is_best_effort` (sparse).

**Mistakes / good-to-know:**
- "At least one of `level` or `term_ids` must be set — calling without either is an error."
- "Results are `(gene × term)` pairs, not distinct genes — use `total_genes` in the response for the gene count. `total_matching` is the row count."
- "Gene-set-size filter is **organism-scoped via descendants**: count of distinct genes annotated to the term or any descendant, for `$organism`. Matches `ontology_landscape`'s convention so tools agree."
- "For GO (a DAG), level slicing is a best-effort approximation — `level_is_best_effort` flags rows where the min-path to root was ambiguous. Check `ontology_landscape`'s `best_effort_share` per level before relying on a GO level."
- "`level_is_best_effort` is a sparse column — absent when not GO / not best-effort. Before boolean filtering in pandas: `df['level_is_best_effort'].fillna(False)`."
- "`organism` is required and single-valued — matches the enrichment surface. Cross-organism browsing: loop the tool, or use `gene_ontology_terms`."
- "Pfam is a 2-level ontology: `level=1` → Pfam domains (leaf), `level=0` → PfamClan (parent). Both Pfam and PfamClan IDs are accepted under `ontology='pfam'`."
- "KEGG: gene edges only hit the KO leaf (`level=3`). Passing `level=0/1/2` rolls up to category/subcategory/pathway via `is_a`."
- "Flat ontologies (`cog_category`, `tigr_role`) have only `level=0`. Pass `level=0` (or `term_ids`). In Mode 2 (`level` only), passing `level >= 1` returns empty `results` with `total_matching=0`. In Mode 3 (`level` + `term_ids`), valid IDs route to the `wrong_level` bucket. Discover which ontologies are flat via `kg_schema`."
- wrong: `genes_by_ontology(ontology='go_bp', organism='MED4')  # no level or term_ids`
  right: `genes_by_ontology(ontology='go_bp', organism='MED4', level=3)`

## Tests

- **Unit (`tests/unit/test_query_builders.py`):** `TestBuildGenesByOntologyDetail` (all 3 modes), `TestBuildGenesByOntologyPerTerm`, `TestBuildGenesByOntologyPerGene`, `TestBuildGenesByOntologyValidate`, `TestHierarchyWalkHelper`.
- **Unit (`tests/unit/test_api_functions.py`):** `TestGenesByOntology` — input validation (ValueError on missing level+term_ids, bad ontology, size bounds), envelope composition, `filtered_out` population, each `wrong_*` bucket.
- **Unit (`tests/unit/test_tool_wrappers.py`):** `TestGenesByOntologyWrapper` — Pydantic round-trip, default `limit=500`, sparse `level_is_best_effort` serialization.
- **Integration (`-m kg`) in `tests/integration/test_mcp_tools.py`:**
  - MED4 × go_bp level=1 → 410 rows / 332 genes / 8 terms (verified 2026-04-14).
  - MED4 × cyanorak_role level=1 → B1's 69-pathway definitions (after filter).
  - Mode 1 with cross-level input → `by_level` breakdown confirms per-level `n_genes` distinctness.
  - `summary=True` → envelope populated, `results=[]`.
- **Regression (`tests/evals/cases.yaml` + `tests/regression/`):** add `genes_by_ontology` to `TOOL_BUILDERS`; regenerate baselines with `--force-regen -m kg`.
- **Cross-tool:** run `scripts/sync_skills.sh` + spot-check regenerated skill reference.

## Migration / breaking-change impact

- **Row shape:** distinct-gene rows → `(gene × term)` long rows. Consumers of `len(results)` as "number of genes" now use `total_genes`.
- **`total_matching` semantics:** was "distinct genes" → now "(gene × term) rows." `total_genes` recovers the old meaning.
- **Required params:** `organism` now required; either `level` or `term_ids` must be supplied (was just `term_ids` required).
- **Row fields:** `organism_name` moved to envelope. `matched_terms`, `gene_summary` removed. `level`, `function_description`, sparse `level_is_best_effort` added.
- **Response envelope:** `n_genes/n_terms` → `total_genes/total_terms`; `by_organism` removed; `by_level`, `top_terms`, `n_best_effort_terms`, `filtered_out`, `wrong_ontology`, `wrong_level` added; `not_found` kept; `not_matched` retired in favor of the split buckets.
- **KEGG:** `ONTOLOGY_CONFIG['kegg']['gene_connects_to_level']` removed — obsolete with the new graph-structure-enforced walk.
- **Skill references:** `skills/multiomics-kg-guide/references/tools/genes_by_ontology.md` regenerated.
- **Chaining mistakes** in sibling YAMLs (`genes_by_function`, `search_ontology`, `gene_ontology_terms`): audited and updated for new row-shape awareness. No semantic conflict.
- **Regression fixtures** regenerated.
- **Research-repo** (out of scope for spec, noted for awareness): `enrich_utils/extraction.py` in B1 uses `genes_by_ontology` as a validation oracle. New shape is strictly richer — validation code migrates by selecting the new `term_id` column.

## Optional fast-path (not in this spec)

Backlog KG change: precompute `t.gene_count_by_organism: map<str,int>` on every ontology-term node ([kg-spec](../../kg-specs/2026-04-14-ontology-term-gene-count-by-organism.md)). When landed, `_hierarchy_walk` can branch on `apoc.meta.type(t.gene_count_by_organism)` to filter candidate terms via map lookup *before* the hierarchy walk, saving a full aggregate per query. Pure optimization; no behavior change; no spec revision needed when it lands.

## Out of scope for this spec

- `ontology_landscape` — already shipped (Child 1). This spec refactors it onto the shared helper but does not change behavior.
- `pathway_enrichment` — Child 3.
- KG rebuild tasks (unified `level:int` landed 2026-04-13; `gene_count_by_organism` is a separate backlog note).
- Research-repo migration of `enrich_utils/extraction.py`.
