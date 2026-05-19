# Tool spec: cluster A — F1 informativeness surface (combined A1 + A2)

## Mode

**Mode B (cross-tool small change).** Spec lists 6+ tools; light Phase 1
(KG iteration done, schema unchanged); Phase 2 briefings instruct each
implementer to "do tool 1 as template, extend to 2..N within your file."

## Purpose

Surface F1 (informativeness) primitives from the 2026-05-01 KG release
across the explorer's tool surface. Two intertwined goals folded into one
spec because they touch the same YAMLs and the AQ semantic-shift note
lands cleanly alongside the new `is_informative` row column:

1. **A1 (semantic-shift docs):** document that `Gene.annotation_quality`
   was redefined from "product-name quality" to "informative-evidence
   richness" (0..3 numeric encoding of `Gene.annotation_state`). The
   existing `min_quality` filter on `genes_by_function` silently shifted
   meaning and its description text is now actively wrong.
2. **A2 (F1 surface):** wire the new fields and per-term flag into the
   tool surface so users can read informativeness metadata on genes,
   filter terms by `is_uninformative`, and see `is_informative` in result
   rows for term-returning tools.

## Out of Scope

- Cluster B (data sources / `contributing_sources`) — separate scope.
- Cluster C (`cluster_type` / `contig` / `seed_ortholog`) — separate scope.
- Cluster D (typed `gene_details`) — separate scope.
- A3 (enrichment defaults + methodology + example python) — separate
  spec, follows this one.
- Renaming `genes_by_function.min_quality` (param → `min_annotation_quality`)
  — surface change deferred; only description updated here.

## Status / Prerequisites

- [x] KG changes landed (2026-05-01 release; verified live 2026-05-04)
- [x] Scope reviewed with user (4-decision pin)
- [x] Cypher snippets drafted + verified against live KG
- [ ] Frozen spec approved
- [ ] Ready for Phase 2

## KG dependencies (verified live 2026-05-04)

| Property / Flag | Coverage |
|---|---|
| `Gene.annotation_state` (enum) | 100% — 99,871 genes, 0 nulls. Distribution: informative_multi=74,214 / no_evidence=10,666 / informative_single=9,855 / catch_all_only=5,136 |
| `Gene.annotation_quality` (0..3 numeric) | matches `annotation_state` exactly (0=10,666, 1=5,136, 2=9,855, 3=74,214) |
| `Gene.informative_annotation_types: list[str]` | 100% populated (sizes 0..13) |
| `<term>.is_uninformative='true'` (sparse) | 224 nodes total across **7 ontology types**: KeggTerm (210), CyanorakRole (5), TigrRole (5), CogFunctionalCategory (1), CellularComponent (1), MolecularFunction (1), BiologicalProcess (1). **Pfam not flagged in current KG** (memory had it; live truth wins). |

No KG schema changes required.

## Tool decisions (4 pinned)

1. **`is_informative: bool` row column** (positive framing, always
   populated). Internally maps from sparse `is_uninformative='true'/null`
   via `coalesce(t.is_uninformative, '') <> 'true' AS is_informative`.
2. **`informative_only` filter is term-side only.** In every tool
   (including enrichment in A3), the filter excludes terms by per-term
   flag. Never touches gene set. ~224 terms get filtered.
3. **`informative_only` defaults:**
   - `False` (opt-in): `gene_ontology_terms`, `genes_by_ontology`, `search_ontology`
   - `True` (opt-out): `ontology_landscape`
4. **Pfam/KeggTerm flag-set is live truth** — no KG-side push-back.

---

## Verified Cypher snippets

All snippets verified against live KG 2026-05-04.

### `informative_only` term filter (universal pattern)

```cypher
WHERE coalesce(t.is_uninformative, '') <> 'true'
```

Verification (Prochlorococcus MED4 direct gene→KEGG):
- Total pairs: 1124, distinct terms: 1017
- Uninformative-flagged pairs: 30 (2.7%)

### `is_informative` row column

```cypher
RETURN ..., coalesce(t.is_uninformative, '') <> 'true' AS is_informative, ...
```

### `gene_overview` new RETURN columns

Detail builder (`build_gene_overview`):
```cypher
RETURN ..., g.annotation_state AS annotation_state,
       coalesce(g.informative_annotation_types, []) AS informative_annotation_types, ...
```

Verification (PMM1428): `annotation_state='informative_multi'`,
`informative_annotation_types=['go_mf', 'pfam']`,
`annotation_quality=3` — confirms the AQ ↔ state encoding.

### `gene_overview` summary builder rollup

`build_gene_overview_summary`:
```cypher
WITH ..., [g IN found | g.annotation_state] AS states
RETURN ..., apoc.coll.frequencies(states) AS by_annotation_state, ...
```

Verification (single-organism filter on Prochlorococcus MED4):
informative_multi=1386 / catch_all_only=292 / informative_single=174 /
no_evidence=124 (1976 total).

### `ontology_landscape` filter (default-on)

When `informative_only=True` (default), append term-level WHERE clause
in the level-rollup so per-(ontology × level) stats reflect informative
terms only. Opt-out via `informative_only=False`.

---

## Per-tool changes

### A1 — semantic-shift docs (no behavior change)

| Target | Layer | Change |
|---|---|---|
| `genes_by_function` | `tools.py:1576-1580` | Rewrite `min_quality` Field description: `"Minimum annotation_quality (0=no_evidence, 1=catch_all_only, 2=informative_single, 3=informative_multi). Use 2 to require ≥1 informative annotation source. Note: this field was redefined in May 2026 KG release."` |
| `gene_overview.yaml` | mistakes | Add: `"annotation_quality is a 0..3 numeric encoding of annotation_state (informative-evidence count). Redefined May 2026 — old semantics conflated product-name quality."` |
| `genes_by_function.yaml` | mistakes | Same |
| `gene_details.yaml` | mistakes | Same |
| `CLAUDE.md` | MCP-tools table | Footnote on the AQ redefinition for `gene_overview`, `gene_details`, `genes_by_function` rows |

### A2 — F1 surface (additive)

#### `gene_overview` (gene-side surface + envelope rollup)

- `kg/queries_lib.py` — `build_gene_overview` RETURN adds
  `annotation_state`, `informative_annotation_types`. `build_gene_overview_summary`
  adds `by_annotation_state` rollup via `apoc.coll.frequencies`.
- `api/functions.py` — pass-through (return-shape changes only).
- `mcp_server/tools.py` — result type adds:
  - `annotation_state: str = Field(description="Informativeness state: informative_multi | informative_single | catch_all_only | no_evidence")`
  - `informative_annotation_types: list[str] = Field(default_factory=list, description="Subset of annotation_types backed by informative (non-catch-all) terms")`
  - Envelope adds `by_annotation_state: list[BreakdownItem]` (rollup of `annotation_state` over result set; unsorted from `apoc.coll.frequencies`, matching existing rollups like `by_organism`).
- `inputs/tools/gene_overview.yaml` — example response shows new fields;
  mistakes entry covers AQ note (above).

#### `gene_ontology_terms` (term-side filter + row)

- `kg/queries_lib.py` — `build_gene_ontology_terms` (leaf + rollup) and
  `build_gene_ontology_terms_summary` add:
  - Param: `informative_only: bool = False`
  - WHERE: append `AND coalesce(t.is_uninformative, '') <> 'true'` when true
  - RETURN: `coalesce(t.is_uninformative, '') <> 'true' AS is_informative`
- `api/functions.py` — thread `informative_only` through.
- `mcp_server/tools.py` — wrapper adds `informative_only: bool = False`
  param; result type adds `is_informative: bool`.
- `inputs/tools/gene_ontology_terms.yaml` — example with `informative_only=True`.

#### `genes_by_ontology` (term-side filter + row)

The 4 builders split distinct roles. `informative_only` and
`is_informative` apply per-builder as follows:

| Builder | `informative_only` filter | `is_informative` in RETURN |
|---|---|---|
| `build_genes_by_ontology_validate` | **No** — validate reports input IDs as-is regardless of informativeness | No |
| `_genes_by_ontology_match_stage` (shared helper) | **Yes** — append `AND ($informative_only = false OR coalesce(t.is_uninformative, '') <> 'true')` before the size_filter WITH (term-level filter must apply before size collapse) | n/a |
| `build_genes_by_ontology_detail` | inherits via helper | **Yes** — RETURN row is per (gene × term) |
| `build_genes_by_ontology_per_term` | inherits via helper | **Yes** — RETURN row is per term |
| `build_genes_by_ontology_per_gene` | inherits via helper | **No** — RETURN row is per gene |

API + wrapper + YAML same shape as `gene_ontology_terms`.

#### `search_ontology` (term-side filter + row)

- `kg/queries_lib.py` — `build_search_ontology` and
  `build_search_ontology_summary`:
  - Param: `informative_only: bool = False`
  - WHERE addition (append to `where_parts`)
  - Detail RETURN adds `is_informative`
- API + wrapper + YAML same shape.

#### `ontology_landscape` (term-side filter, default-on)

- `kg/queries_lib.py` — `build_ontology_landscape`:
  - Param: `informative_only: bool = True`
  - WHERE: filter terms by per-term flag in the level-rollup
- API + wrapper + YAML — wrapper param `informative_only: bool = True`;
  YAML example documents opt-out via `informative_only=False`.
- **No row-level `is_informative`** — landscape returns aggregated
  per-(ontology × level) stats, not per-term rows.

---

## Implementation Order (Phase 2)

| Step | Layer | File | Agent |
|------|-------|------|-------|
| 1 | RED tests | `tests/unit/test_query_builders.py`, `test_api_functions.py`, `test_tool_wrappers.py` (+ `EXPECTED_TOOLS`, `TOOL_BUILDERS`) | `test-updater` |
| 2a | Query builders | `kg/queries_lib.py` (5 builder pairs ≈ 10 builders) | `query-builder` |
| 2b | API functions | `api/functions.py` (5 functions) | `api-updater` |
| 2c | MCP wrappers | `mcp_server/tools.py` (5 wrappers + `min_quality` description fix) | `tool-wrapper` |
| 2d | About content | 7 yamls + CLAUDE.md + regen | `doc-updater` |
| 3 | Verify | code-reviewer (parallel); pytest unit/integration/regression with `--force-regen` | orchestrator |

## Test scope (per layer — `test-updater` will translate)

### Query builder
- `gene_overview`: `annotation_state` + `informative_annotation_types` in compact RETURN; summary `by_annotation_state` is non-empty list of {value,count} dicts.
- Per ontology builder: `informative_only=True` adds the WHERE clause; `is_informative` in RETURN cols.
- `ontology_landscape`: default `informative_only=True` filters; `False` doesn't.

### API
- Pass-through tests: `informative_only` reaches the builder.

### Tool wrapper
- All 4 ontology tool wrappers expose `informative_only` param.
- `gene_overview` response includes `by_annotation_state` envelope key.
- All 4 ontology result models include `is_informative: bool`.

### Regression
- All 5 affected tools rebaselined via `--force-regen -m kg`.

### Integration (smoke tests against live KG)
- `gene_overview(["PMM1428"])` returns `annotation_state='informative_multi'`, `informative_annotation_types=['go_mf', 'pfam']`.
- `gene_ontology_terms(..., ontology="kegg", organism="Prochlorococcus MED4", informative_only=True)` returns 1094 leaf-mode rows; `informative_only=False` returns 1124. Filter effect: 30 rows.
- `gene_ontology_terms(..., ontology="cyanorak", informative_only=True)` exhibits a much larger filter effect (16.5% of pairs flagged genome-wide) — useful contrast in test cases.
- `ontology_landscape()` (default `informative_only=True`) reflects fewer terms than `informative_only=False`. Concrete delta to capture in baseline.

## Special handling

- **No new tools.** Surface-additive only.
- **Param naming:** `genes_by_function.min_quality` preserved (rename
  deferred; surface change). Only description updated.
- **`is_informative` is required (non-Optional) bool** in the
  wrapper-level Pydantic result model. The KG flag is sparse
  (`'true'` or absent); the Cypher RETURN coerces to bool via
  `coalesce(...)<>'true'` so the value is always populated.
- **`ontology_landscape` default flip is a behavioral change.** Default
  `informative_only=True` will reduce row counts for downstream callers
  that don't pass the param. Existing regression baselines (refreshed
  in cluster Z, commit b83b7f9) WILL need rebaselining via
  `--force-regen` after A2 lands. Mention in agent briefing for
  doc-updater + tool-wrapper.
- **Mode B briefing distinction:** `gene_overview` is a parallel small
  change on the gene side (2 RETURN columns + 1 envelope rollup). The
  4 ontology tools share the term-side pattern (same WHERE/RETURN
  delta repeated). Brief query-builder agent: "Implement
  `gene_ontology_terms` as the term-side template, then mechanically
  extend to `genes_by_ontology` (4 builders), `search_ontology`,
  `ontology_landscape`. `gene_overview` is independent — handle as a
  parallel small change."
- **Anti-scope-creep guardrail (mandatory in agent briefings):** ADD
  only — do NOT modify, rename, or rebaseline any existing test, case,
  or YAML entry. If an unrelated test fails, REPORT AS A CONCERN.

## Documentation Updates

| File | What |
|------|------|
| `CLAUDE.md` | Footnote/flag for AQ redefinition (3 tool rows: gene_overview, genes_by_function, gene_details) |
| `inputs/tools/gene_overview.yaml` | New fields in example response; AQ-redef mistake entry |
| `inputs/tools/genes_by_function.yaml` | AQ-redef mistake entry |
| `inputs/tools/gene_details.yaml` | AQ-redef mistake entry |
| `inputs/tools/gene_ontology_terms.yaml` | `informative_only=True` example |
| `inputs/tools/genes_by_ontology.yaml` | `informative_only=True` example |
| `inputs/tools/search_ontology.yaml` | `informative_only=True` example |
| `inputs/tools/ontology_landscape.yaml` | `informative_only=False` opt-out example |
| Regen | `uv run python scripts/build_about_content.py` |

## Sign-off

After spec freeze, Phase 2 dispatches the test-updater agent first (RED),
then the 4 implementer agents in parallel (GREEN), then code review
+ pytest unit/integration/regression (VERIFY).
