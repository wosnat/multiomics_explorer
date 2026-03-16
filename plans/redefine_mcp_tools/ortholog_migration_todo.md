# Ortholog Migration: Explorer Changes

Tracks all explorer-side changes needed after the KG switched from pairwise
homolog edges to OrthologGroup cluster nodes. See `kg_homolog_redesign.md`
for rationale and `/home/osnat/github/multiomics_biocypher_kg/docs/explorer_ortholog_migration.md`
for the KG-side migration guide with Cypher translation table.

---

## Small Changes (mechanical updates, no design decisions) — DONE

All completed and verified (495 tests passing).

### Config files

- [x] **schema_baseline.yaml** — Removed old elements, added `OrthologGroup` + `Gene_in_ortholog_group`.
- [x] **prompts.yaml** — Updated expression edge listing (2 types, not 4), homology section rewritten for OrthologGroup model.

### Documentation

- [x] **AGENT.md** — Replaced `Cyanorak_cluster`, `Gene_is_homolog_of_gene`, `Gene_in_cyanorak_cluster` with `OrthologGroup` + `Gene_in_ortholog_group`. Updated pitfalls.
- [x] **CLAUDE.md** — No changes needed (tool descriptions still accurate).

### Raw Cypher queries (queries.py)

- [x] **`ORTHOLOG_EXPRESSION_EDGE_COUNT`** → replaced with `ORTHOLOG_GROUP_COUNT`.
- [x] **`HOMOLOG_EDGE_COUNT`** → replaced with `ORTHOLOG_MEMBERSHIP_EDGE_COUNT`.
- [x] **`HOMOLOGS_OF_GENE`** → rewritten with OrthologGroup 2-hop pattern.
- [x] **Few-shot example** — Updated to OrthologGroup traversal pattern.

### Query builders (queries_lib.py)

- [x] **`ORTHOLOG_EXPR_RELS` / `ALL_EXPR_RELS`** — Removed.
- [x] **`build_get_gene_details_main()`** — Now fetches `OrthologGroup` via `Gene_in_ortholog_group`, returns `_ortholog_groups` list.
- [x] **`build_get_gene_details_homologs()`** — 2-hop OrthologGroup pattern, returns `source` + `taxonomic_level`.
- [x] **`build_get_homologs()`** — Basic 2-hop update (minimal, pending full redesign).
- [x] **`build_query_expression()`** — Removed `include_orthologs` parameter.
- [x] **`build_search_genes()`** — Removed `cluster_id` column (was `coalesce(cluster_number, alteromonadaceae_og)`).

### MCP tool wrappers (tools.py)

- [x] **`query_expression()`** — Removed `include_orthologs` parameter.
- [x] **`get_gene_details()`** — Updated docstring.

### Tests & fixtures

- [x] **test_query_builders.py** — All assertions updated for new patterns.
- [x] **test_tool_correctness.py** — Mock data updated (`_ortholog_groups` replaces `_cluster`), removed `include_orthologs` test.
- [x] **test_tool_wrappers.py** — Removed `include_orthologs` test.
- [x] **fixtures/gene_data.py** — Removed `cluster_id` from `as_search_genes_result()`.
- [x] **integration/test_tool_correctness_kg.py** — Updated gene details and homolog tests.
- [x] **integration/test_mcp_tools.py** — Replaced orthologs test with direct expression test.
- [x] **evals/cases.yaml** — Updated expected columns throughout.
- [x] **regression YAML baselines** — Regenerated with `--force-regen`.

---

## Requires Planning (design decisions, multiple approaches possible)

### `get_homologs` tool — full rewrite

Currently has a basic 2-hop OrthologGroup traversal (working but minimal).
Needs full redesign with:

**Design decisions needed:**
- Distance computation: query-time CASE on organism taxonomy (Option A from redesign doc) vs. OrthologGroup taxonomic_level as proxy (Option B). Redesign doc recommends A for get_homologs, B for expression queries.
- Filtering: expose `source` and `taxonomic_level` as user-facing filters? Current tool has no source filter.
- Paralog handling: large Bacteria-level COGs include same-organism paralogs. Filter `WHERE other.organism_strain <> g.organism_strain` by default?
- Return shape: replace `distance`/`cluster_id`/`source` columns with `taxonomic_level`/`source`/`og_name`?

### `search_genes` dedup logic

Dedup currently no-ops (no `cluster_id` in results). Needs OrthologGroup-based grouping.

**Design decisions needed:**
- Which OrthologGroup level to use for dedup grouping (lowest-level OG? Cyanorak? all?).
- How to pick a representative gene per group.
- Performance: adding an OrthologGroup join to every search query may not be worth it if dedup is rarely used.

### `query_expression` / `compare_conditions` ortholog mode

The `include_orthologs` parameter has been removed. Ortholog expression lookup
needs reimplementation as a 3-hop join through OrthologGroup.

**Design decisions needed:**
- Whether to use OrthologGroup taxonomic_level as the homology qualifier (Option B) or full organism distance.
- How to present the homology provenance in results (source + level columns).
- Whether `include_orthologs` should accept a level filter (e.g. only Cyanorak orthologs, or only same-family).
