# Plan: Rename `find_gene` → `search_genes` + Improvements

Review of live KG + explorer code (2026-03-15). Covers explorer-side changes
to the `find_gene` tool: rename, new return columns, deduplication, and category
filtering.

## Status after KG rebuild

These items from `docs/kg_changes_find_gene.md` are confirmed done in the current KG:

- [x] Fulltext index slimmed to 4 fields: `gene_summary`, `gene_synonyms`, `alternate_functional_descriptions`, `pfam_names`
- [x] `gene_summary` cleaned — identifier-style gene_names dropped, DUF best_desc stripped
- [x] `annotation_quality` recomputed with real 0/1/2/3 scoring (5206 / 3689 / 5021 / 21310)
- [x] `find_gene` returns `function_description` instead of `gene_summary`
- [x] `min_quality` docstring updated with real 0/1/2/3 scale
- [x] Regression baselines regenerated against new KG
- [x] Test fixtures regenerated
- [x] `gene_category` property added — 25 categories, 100% coverage (35,226 genes)
- [x] `gene_name` cleaned — identifiers (RefSeq-style, locus_tag duplicates) set to null (16,358 genes now null)

## Issues found in review

### ~~A. `gene_name` shows identifiers instead of real names~~ (fixed in KG)

Cleaned at source — 0 RefSeq-style gene_names, 0 gene_name=locus_tag remaining.

### ~~B. Truncated `function_description` values~~ (not a bug)

Example: `function_description: ")-iron permease"`. This is valid eggNOG
terminology — comes straight from the annotation file. Not a KG build artifact.

### C. No way to see what the index matched

`find_gene` returns `product` and `function_description` but not `gene_summary`,
which is the primary indexed field. When `uspG` (universal stress protein) matches
"oxidative stress", the caller can't see *why* — the match came from
`alternate_functional_descriptions`, not from the returned fields.

### D. Ortholog flooding

Searching "naphthoate" returns 8 identical `menB` orthologs from different strains.
Users searching by function want distinct functions, not every copy.

---

## Tool signature (after all changes)

```python
@mcp.tool()
def search_genes(
    ctx: Context,
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
    deduplicate: bool = False,
    limit: int = 10,
) -> str:
    """Free-text search across gene functional annotations using full-text index.
    Supports Lucene syntax: "DNA repair", nitrogen AND transport, iron*, dnaN~.

    Args:
        search_text: Free-text query (Lucene syntax supported).
        organism: Optional organism filter (e.g. "MED4", "Prochlorococcus MED4").
            Use list_organisms to see all valid organisms.
        category: Optional gene_category filter (e.g. "Photosynthesis", "Transport").
            Use list_filter_values to see all valid categories. Invalid values
            return empty results (no validation).
        min_quality: Minimum annotation_quality (0-3).
            0 = hypothetical, no function info;
            1 = hypothetical but has function description;
            2 = real product name;
            3 = well-annotated (product + GO/KEGG/EC/Pfam).
            Use 2 to skip hypothetical proteins.
        deduplicate: If True, collapse orthologs by cluster and return one
            representative per cluster with collapsed_count and
            cluster_organisms summary. Counts reflect hits within the result
            set, not total cluster membership — use get_homologs for full
            ortholog inventory.
        limit: Max results (default 10, max 50). When deduplicate=True, the
            limit applies to the pre-dedup query, so fewer rows may be
            returned after collapsing.
    """
```

**Return columns:**
`locus_tag`, `gene_name`, `product`, `function_description`, `gene_summary`,
`organism_strain`, `annotation_quality`, `cluster_id`, `score`

When `deduplicate=True`, each clustered row also gets:
- `collapsed_count`: number of search hits collapsed into this representative
  (within the result set, not total cluster size)
- `cluster_organisms`: `{"Prochlorococcus MED4": 1, ...}` per-organism breakdown

---

## Explorer-side changes

### 0. Rename `find_gene` → `search_genes`

**Files:** `tools.py`, `queries_lib.py`, all test files, `CLAUDE.md`,
`cases.yaml`, `test_regression.py`, regression baselines

Rename the tool and builder:
- `find_gene` → `search_genes` (MCP tool name)
- `build_find_gene` → `build_search_genes` (query builder)

No fixture helper `as_find_gene_result` exists — a new `as_search_genes_result`
helper will be created in step 6 (tests).

**Why:** `find_gene` is ambiguous — could mean "find by ID" (that's `resolve_gene`)
or "search annotations." `search_genes` clearly signals fulltext search and pairs
with `resolve_gene` (exact ID lookup).

### 1. Add `gene_summary` to search_genes results

**Files:** `queries_lib.py`

Add `g.gene_summary AS gene_summary` to the RETURN clause of `build_search_genes`.
Shows the caller what the fulltext index actually scored against.

### ~~2. Mask identifier-style gene_names~~ (no longer needed)

K1 done — `gene_name` cleaned at source in KG.

### 3. Return cluster info in search_genes results

**Files:** `queries_lib.py`

Add a `cluster_id` column that works across all organisms. The KG has three
homolog edge sources, all on `Gene_is_homolog_of_gene` with a uniform
`{source, cluster_id, distance}` schema:

| source | cluster_id | organisms |
|--------|-----------|-----------|
| `cyanorak_cluster` | Cyanorak cluster number | Pro ↔ Pro, Syn ↔ Syn, Pro ↔ Syn |
| `eggnog_alteromonadaceae_og` | eggNOG OG ID (e.g. `46B1B@72275,Alteromonas...`) | Alt ↔ Alt |
| `eggnog_bacteria_cog_og` | COG OG ID | Alt ↔ Pro/Syn (cross-phylum) |

Pro/Syn also have `Gene_in_cyanorak_cluster → Cyanorak_cluster` edges and a
`cluster_number` property on the Gene node. Alteromonas has `alteromonadaceae_og`
as a Gene property.

**Approach — use Gene properties directly** (avoids expensive OPTIONAL MATCH
on homolog edges in a fulltext query):

```cypher
RETURN ...,
       coalesce(g.cluster_number, g.alteromonadaceae_og) AS cluster_id,
       ...
```

This gives cluster grouping for Pro/Syn (via `cluster_number`, 87-96%) and
Alteromonas (via `alteromonadaceae_og`, 85% = 10,403/12,195). Genes with
neither get `null` and appear individually in dedup.

**Note:** Cyanorak cluster numbers and eggNOG OG IDs use different naming
schemes (e.g. `CK_00000364` vs `46B1B@72275`), so collisions are not possible.

### 4. Add optional deduplication by cluster

**Files:** `tools.py`

Add `deduplicate: bool = False` parameter to `search_genes`. When True, group
results by `cluster_id` and return only the top-scoring representative per
cluster. Genes without a `cluster_id` always appear individually.

Depends on step 3 (cluster_id must be in results).

**Implementation — post-query in Python (not Cypher):**

```python
if deduplicate:
    cluster_groups: dict[str, list] = {}
    deduped = []
    for row in results:
        cluster = row.get("cluster_id")
        if cluster:
            if cluster in cluster_groups:
                cluster_groups[cluster].append(row)
                continue
            cluster_groups[cluster] = [row]
        deduped.append(row)
    # Add cluster summary to each representative
    for row in deduped:
        cluster = row.get("cluster_id")
        if cluster:
            group = cluster_groups[cluster]
            row["collapsed_count"] = len(group)
            # Count genes per organism
            org_counts: dict[str, int] = {}
            for r in group:
                org = r.get("organism_strain", "Unknown")
                org_counts[org] = org_counts.get(org, 0) + 1
            row["cluster_organisms"] = org_counts
    results = deduped
```

Results are already sorted by score DESC, so first hit per cluster is the best.
Each representative gets:
- `collapsed_count`: number of search hits collapsed into this representative
  (e.g. 8 for `menB` if all 8 orthologs appeared in results)
- `cluster_organisms`: per-organism breakdown, e.g.
  `{"Prochlorococcus MED4": 1, "Prochlorococcus MIT9313": 1, "Synechococcus WH8102": 1, ...}`

Genes without a cluster get neither field. Works for both Cyanorak clusters
(Pro/Syn) and eggNOG OGs (Alteromonas).

**Limit interaction:** The `limit` parameter applies to the Neo4j query
(pre-dedup). With `limit=10` and `deduplicate=True`, the query returns 10 rows
from Neo4j, then dedup may collapse some, yielding fewer final rows. This is
acceptable — the alternative (over-fetching to guarantee N deduped rows) adds
complexity for marginal benefit.

### 5. Add `category` filter

**Files:** `tools.py`, `queries_lib.py`

Add `category: str | None = None` parameter. Filter on `g.gene_category`:

```cypher
AND ($category IS NULL OR g.gene_category = $category)
```

Invalid category values silently return empty results (no server-side
validation). The docstring directs users to `list_filter_values` for valid
categories.

### 6. Update tests

Tests follow the project test structure (see `/update-tests` skill):
unit → integration → eval/regression snapshots.

#### Unit tests

**`tests/unit/test_query_builders.py`:**
- Verify `gene_summary` in RETURN clause
- Verify `cluster_id` via COALESCE in RETURN clause
- Verify `$category` parameter and WHERE clause when `category` provided
- Verify `$category IS NULL` when `category=None`

**`tests/fixtures/gene_data.py`:**
- Create new `as_search_genes_result()` helper (no existing helper to rename)
  that includes `gene_summary`, `cluster_id`, and `score` columns
- Ensure Alteromonas fixture genes include `alteromonadaceae_og` property
  (currently missing from fixtures — needs to be added)
- Update `scripts/build_test_fixtures.py` to match

**`tests/unit/test_tool_wrappers.py`:**
- Mock results with duplicate clusters, verify dedup logic:
  - `collapsed_count` correct
  - `cluster_organisms` has per-organism counts
  - Genes without cluster_id appear individually
- Verify `category` param passed through to builder

**`tests/unit/test_tool_correctness.py`:**
- Rename `TestFindGeneCorrectness` → `TestSearchGenesCorrectness`
- Update all `tool_fns["find_gene"]` calls → `tool_fns["search_genes"]`
- Update tool name in `test_all_tools_registered` list

#### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

**Cluster_id across organisms:**
- Pro/Syn gene gets Cyanorak cluster_number as cluster_id
- Alteromonas gene gets eggNOG OG as cluster_id
- Gene with neither has `null` cluster_id

**Deduplication:**
- Search "photosystem" with `deduplicate=True`, verify fewer rows than without
- Search "chaperone" with `deduplicate=True`, verify results span both
  Prochlorococcus and Alteromonas (htpG has orthologs in both)

**Category filter:**
- Search "polymerase" with `category="Replication and repair"` — all results
  have that category
- Search "transport" with `category="Photosynthesis"` — returns fewer results
  than without category filter

**Cross-organism (no organism filter):**
- Search "chaperone" — top 10 includes both Prochlorococcus (dnaK2, htpG) and
  Alteromonas (htpG) genes
- Search "catalase" — returns Alteromonas only (no catalase in cyanobacteria)
- Search "superoxide dismutase" — returns both Pro/Syn (sodN) and Alteromonas (sodN)

#### Eval cases (`tests/evals/cases.yaml`)

```yaml
# --- cluster_id ---

- id: search_genes_with_cluster_id
  tool: search_genes
  desc: Results include cluster_id for ortholog grouping
  params:
    search_text: naphthoate
    limit: 10
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, function_description,
              gene_summary, organism_strain, annotation_quality,
              cluster_id, score]

# --- deduplication ---

- id: search_genes_dedup_photosystem
  tool: search_genes
  desc: Dedup collapses photosystem orthologs into cluster representatives
  params:
    search_text: photosystem
    deduplicate: true
    limit: 20
  expect:
    min_rows: 1
    # limit=20 pre-dedup; expect fewer rows after collapsing orthologs

- id: search_genes_dedup_naphthoate
  tool: search_genes
  desc: Dedup collapses 8 menB orthologs into ~1-2 clusters
  params:
    search_text: naphthoate
    deduplicate: true
    limit: 10
  expect:
    min_rows: 1
    max_rows: 3

# --- category filter ---

- id: search_genes_category_filter
  tool: search_genes
  desc: Category filter restricts to Photosynthesis genes
  params:
    search_text: reaction centre
    category: Photosynthesis
  expect:
    min_rows: 1

# --- cross-organism ---

- id: search_genes_cross_organism_chaperone
  tool: search_genes
  desc: "chaperone" spans Pro + Syn + Alt in top results
  params:
    search_text: chaperone
    limit: 10
  expect:
    min_rows: 5
    columns: [locus_tag, gene_name, product, organism_strain, score]
    # Should include both Prochlorococcus and Alteromonas htpG

- id: search_genes_cross_organism_superoxide
  tool: search_genes
  desc: "superoxide dismutase" spans Pro/Syn + Alt
  params:
    search_text: superoxide dismutase
    limit: 10
  expect:
    min_rows: 3
    # Should include sodN from Synechococcus and Alteromonas

- id: search_genes_alteromonas_only_catalase
  tool: search_genes
  desc: "catalase" returns Alteromonas only (not in cyanobacteria)
  params:
    search_text: catalase
    limit: 10
  expect:
    min_rows: 5
    # All results should be Alteromonas

- id: search_genes_dedup_cross_organism_chaperone
  tool: search_genes
  desc: Dedup chaperone collapses orthologs but keeps both Pro + Alt representatives
  params:
    search_text: chaperone
    deduplicate: true
    limit: 10
  expect:
    min_rows: 2
    # Should still have both organisms after dedup
```

#### Regression snapshots (`tests/regression/`)

All existing `find_gene_*` baselines must be regenerated — both because of the
rename and because RETURN columns change (added `gene_summary`, `cluster_id`).
After implementing:

```bash
# Regenerate baselines
pytest tests/regression/ --force-regen -m kg

# Verify baselines pass
pytest tests/regression/ -m kg
```

Dedup cases can't use `TOOL_BUILDERS` directly (dedup is post-query Python
logic). Options:
- Test dedup snapshots via tool wrapper in integration tests
- Or add a dedicated regression path in `test_regression.py` that calls
  the full tool wrapper

---

## KG-side changes

### ~~K1. Clean `gene_name` at source~~ (done)

Live in KG — 0 RefSeq-style, 0 gene_name=locus_tag. 16,358 genes now have
`gene_name = null`.

### ~~K2. Fix truncated `function_description` values~~ (not a bug)

The `")-iron permease"` pattern is valid eggNOG terminology, not a build artifact.

### ~~K3. `gene_category` property~~ (done)

Live in KG — 25 categories, 100% coverage. Explorer can now add a `category`
filter to `search_genes`.

---

## Implementation order

| Order | Change | Where | Plan |
|-------|--------|-------|------|
| ~~1~~ | ~~K1: Clean `gene_name`~~ | ~~KG~~ | done |
| 2 | Rename `find_gene` → `search_genes` | Explorer | this file |
| 3 | Add `gene_summary` to return | Explorer | this file |
| ~~4~~ | ~~Mask identifier gene_names~~ | ~~Explorer~~ | not needed (K1 done) |
| 5 | `cluster_id` + dedup | Explorer | this file |
| 6 | Add `category` filter | Explorer | this file |

Steps 2, 3, and 6 can proceed in parallel. Step 5 (dedup) depends on step 3
(cluster_id must be in the RETURN clause before dedup can use it).

## Out of scope

- Changes to `resolve_gene`, `get_gene_details`, or other existing tools
- KG schema changes beyond the properties listed above
- New MCP tools (`list_organisms`, `list_filter_values`, `find_genes_by_function`)
  — see separate plans in this directory
- Vector embeddings + semantic search — see
  [vector_embeddings_semantic_search.md](vector_embeddings_semantic_search.md)
