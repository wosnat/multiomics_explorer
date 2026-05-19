# A3 — Enrichment defaults: `informative_only=True` + `is_informative` per-row

**Date:** 2026-05-04
**Mode:** B (cross-tool small change — `pathway_enrichment` + `cluster_enrichment`)
**Cluster:** A3 of the explorer-side surface refresh (paired with A1/A2, merged 2026-05-04 via 8bbbcbb)
**KG asks:** none. Mechanism (`is_uninformative` term flag + `genes_by_ontology` `informative_only` filter + per-row `is_informative` carry) all landed pre-Cluster A.

## Goal

Bring the two enrichment surfaces (`pathway_enrichment`, `cluster_enrichment`) to parity with the rest of Cluster A's F1 informativeness work:

1. Default `informative_only=True` — uninformative terms (e.g. KEGG map00001 "metabolic pathways", GO root `go:0008150`) excluded by default from Fisher tests.
2. Surface `is_informative: bool` per result row so callers can diagnose / post-filter even when running with `informative_only=False`.

## Why

Cluster A2 established `informative_only` on the four browse/discovery surfaces (`gene_ontology_terms`, `genes_by_ontology`, `search_ontology`, `ontology_landscape`). Enrichment was deferred to A3 because it's a default-flip with downstream behavior change (Fisher denominators shift) and warrants its own focused build.

The case for **default `True`** rather than opt-in:
- Uninformative terms (genome-roots, "metabolic pathways" maps with 800+ genes) are noise in over-representation testing. Most callers want them excluded.
- `ontology_landscape` already defaults `True`. Keeping enrichment opt-in would create a "discovery says X is rank-1, enrichment includes it anyway" inconsistency.
- Cluster A's lesson #2 (default flips can quietly break tests pinning prior behavior) applies — addressed via the `[ENR]` flag in CLAUDE.md and YAML mistake entries.

The case for **per-row `is_informative`**:
- Same parity argument. Browse tools surface it; enrichment tools should too.
- Enables diagnostic flows: run with `informative_only=False`, sort by p-value, post-filter on `is_informative` to compare informative-only vs full ranks without two API calls.

## Design

### Decisions locked

| Q | Decision |
|---|---|
| Default value | `informative_only: bool = True` on both tools |
| CLAUDE.md surface | `[ENR]` markers + footnote on both rows; "default-flip" mistake entry in both YAMLs |
| Example scope | Side-by-side `True` vs `False` demo block in `examples/pathway_enrichment.py` |
| Per-row surface | `is_informative: bool` field on both Pydantic result classes |

### Layer touch summary

| Layer | File | Change |
|---|---|---|
| KG | `kg/queries_lib.py` | none — already supports `informative_only` and emits `is_informative` |
| Analysis | `analysis/enrichment.py` | none — `fisher_ora` (lines 367–374) already auto-passes through any term2gene columns other than `term_id/term_name/locus_tag` |
| API | `api/functions.py::pathway_enrichment` (line 4270) | Add `informative_only: bool = True`; thread to internal `genes_by_ontology(...)` call (currently line 4363); record in `result.params` |
| API | `api/functions.py::cluster_enrichment` (line 4455) | Same shape |
| MCP | `mcp_server/tools.py::pathway_enrichment` (line 5543) | Add `Annotated[bool, Field(default=True, description=...)]`; thread through |
| MCP | `mcp_server/tools.py::cluster_enrichment` (line 5666) | Same |
| MCP | `PathwayEnrichmentResult` (line 28) | Add `is_informative: bool` field after `level` |
| MCP | `ClusterEnrichmentResult` (line 267) | Same |

**Why `analysis/enrichment.py` is untouched.** `fisher_ora` already iterates `term2gene.columns` and auto-merges every column that isn't a structural key:

```python
# multiomics_explorer/analysis/enrichment.py:367-374
passthrough_cols = [
    c for c in term2gene.columns
    if c not in {"term_id", "term_name", "locus_tag"}
]
...
first_rows = term2gene.drop_duplicates("term_id").set_index("term_id")
```

`is_informative` is already a column on `genes_by_ontology` detail rows. Once `pathway_enrichment` / `cluster_enrichment` invoke `genes_by_ontology`, the column flows into `term2gene`, then into `result.results`, then into the MCP envelope automatically. No analysis-layer signature change.

### Filter semantics

**Term-side only.** Never restricts the gene set, the background, or the DE inputs. Identical contract to `ontology_landscape` and the three browse tools. The filter is applied inside `genes_by_ontology` at the term-MATCH stage (`coalesce(t.is_uninformative, '') <> 'true'`) BEFORE `min_gene_set_size` collapse.

### Pydantic field shape

```python
# PathwayEnrichmentResult and ClusterEnrichmentResult, after `level`:
is_informative: bool = Field(
    description=(
        "True if the term is not flagged is_uninformative in the KG. "
        "Always present, regardless of informative_only setting, so "
        "callers can post-filter or diagnose. With default informative_only=True, "
        "all rows have is_informative=True by construction; pass "
        "informative_only=False to opt out and see uninformative terms."
    ),
)
```

Required field (not Optional). Every term in the KG has a definite informative state; coalesce-on-null in the Cypher gives `False` only for explicit `is_uninformative='true'` flags, `True` otherwise.

### About-content

| File | Change |
|---|---|
| `inputs/tools/pathway_enrichment.yaml` | New param doc; default-flip mistake entry: "Caller pinning row counts from pre-2026-05 runs sees fewer rows by default. Pass `informative_only=False` to restore old behavior, or accept the new default (recommended)." Link in `chaining` section to `enrichment.md`. (`is_informative` is a required compact-tier field — auto-documented from the Pydantic Field description, not in `verbose_fields`.) |
| `inputs/tools/cluster_enrichment.yaml` | Same |
| `skills/multiomics-kg-guide/references/analysis/enrichment.md` | New `## Informative-only filtering (default 2026-05)` section: rationale, term-side-only semantics, Fisher denominator behavior, opt-out guidance, KG drift caveat (if KG flags shift, prior runs become non-reproducible — pin via param). |
| `examples/pathway_enrichment.py` | New `demo_informative_only()` block: same call with `informative_only=True` (default) and `False`; print `len(result.results)` for each plus a `head()` showing `is_informative` column to surface the row-count delta. |
| `CLAUDE.md` MCP-tools table | `[ENR]` markers on `pathway_enrichment` + `cluster_enrichment` rows. Footnote: "`[ENR]` Default `informative_only=True` as of 2026-05 release — uninformative terms (e.g. KEGG map00001 'metabolic pathways', GO root go:0008150) excluded by default. Pass `informative_only=False` to opt out. Per-row `is_informative` surfaced for diagnosis." |

After edits: `uv run python scripts/build_about_content.py` regenerates the md (writes directly under `skills/multiomics-kg-guide/references/tools/`).

### Test surface

**Stage 1 RED** — new failing tests across 3 layered files; cross-file fixture cascade per Cluster A lesson #3.

| File | New tests | Notes |
|---|---|---|
| `tests/unit/test_query_builders.py` | `TestPathwayEnrichmentBuilderInformativeOnly`, `TestClusterEnrichmentBuilderInformativeOnly` | Builders themselves unchanged; tests verify api → `genes_by_ontology` threading via mocks. Light coverage. |
| `tests/unit/test_api_functions.py` | `TestPathwayEnrichmentInformativeOnly`, `TestClusterEnrichmentInformativeOnly`. Cases: (a) default `True` excludes uninformative term rows; (b) `informative_only=False` includes them; (c) `result.params["informative_only"]` is recorded with the requested value; (d) `is_informative` column present in `result.results` DataFrame. | Use mocked `genes_by_ontology` returns with mixed informative/uninformative term rows. |
| `tests/unit/test_tool_wrappers.py` | `TestPathwayEnrichmentInformativeOnlyWrapper`, `TestClusterEnrichmentInformativeOnlyWrapper`. Cases: MCP wrapper threads `informative_only`; `is_informative` field present on per-row Pydantic models; field is required (Pydantic raises if missing). | |
| `tests/fixtures/*.py` | Extend any fixture constructing `PathwayEnrichmentResult` / `ClusterEnrichmentResult` instances to include `is_informative=True`. Pydantic will fail validation without it. | Required-field Pydantic cascade — same shape as Cluster A's `OntologyTermBreakdown` cascade. |
| `tests/unit/test_tool_correctness.py` | If `_SAMPLE_API_RETURN` for either tool is constructed inline (or a helper builds per-row dicts), extend with `is_informative`. | |
| `tests/unit/test_api_contract.py` | Update `expected_keys` for `result.params` — new `informative_only` key in both tools. | |

**Stage 3 VERIFY**:
1. `superpowers:requesting-code-review` (background) — **hard gate**, mocks can't validate Cypher.
2. `pytest tests/unit/ -q`
3. `pytest tests/integration/ -m kg -q`
4. `pytest tests/regression/ --force-regen -m kg -q` then `pytest tests/regression/ -m kg -q` — rebaselines `pathway_enrichment_med4_cyanorak_level1_10exp.yml`. Default-True drops uninformative term rows; expected fewer rows in the new baseline.

### Anti-scope-creep guardrails (mandatory in every Stage-2 brief)

```
ADD only — do NOT modify, rename, or rebaseline any existing test, case, or yml.
If an unrelated test fails in your environment, REPORT AS A CONCERN; do not silently
retune. Pinned baselines are KG-state guards.
```

Mode B briefing: "Implement `pathway_enrichment` as the template within your file, then extend to `cluster_enrichment` (parallel small change — same param, same threading pattern, same `is_informative` field placement)."

### Out of scope

- New `cluster_enrichment` regression baseline (gap exists today — separate concern; surface to user post-A3, not bundled).
- `fisher_ora` signature changes (auto-passthrough handles it).
- Background gene-set logic (filter is term-side only).
- Cluster B (F2 data sources), Cluster C (F3/F4 vocab fills), Cluster D (typed `gene_details`) — separate skill runs.

## Phase 2 dispatch

| Stage | Action |
|---|---|
| Stage 1 RED | One `test-updater` agent. Brief enumerates all 6 test/fixture files above. Expect new tests red, rest green. Halt if unrelated red. |
| Stage 2 GREEN | 4 implementer agents in **one** message, parallel: `query-builder` (no-op confirmation that builders need no change), `api-updater`, `tool-wrapper`, `doc-updater`. Each gets Mode B template-and-extend framing + anti-scope-creep guardrail. |
| Stage 3 VERIFY | `superpowers:requesting-code-review` (background) + 3 foreground pytest gates + regression regen + `superpowers:verification-before-completion` + `superpowers:finishing-a-development-branch`. |

## References

- Cluster A1+A2 spec: `docs/superpowers/specs/2026-05-01-kg-side-frictions-reframed.md` (friction context)
- Cluster A merge: commit `8bbbcbb` on main (2026-05-04)
- Plan source of A3 scope: `project_explorer_surface_refresh_paused.md` (memory)
- Cluster A retrospective: `project_cluster_a_shipped.md` (memory) — five lessons applied to A3 brief shape
- KG release: `project_kg_2026_05_release.md` (memory) — KG-side mechanism for F1
- Add-or-update-tool skill: `.claude/skills/add-or-update-tool/SKILL.md` (Mode B flow)
