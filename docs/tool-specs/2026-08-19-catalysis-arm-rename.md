# Catalysis-arm count rename — gene_overview, list_organisms, list_metabolites (Mode B)

**Date:** 2026-08-19 · **Mode:** B (cross-tool small change) · **Status:** DRAFT — awaiting freeze
**Driver:** KG-SYNC-001 ([presync asks](../kg-specs/2026-08-19-presync-kg-asks.md) §3/§8) — the KG retired `Gene.metabolite_count`, `OrganismTaxon.metabolite_count`, `Metabolite.gene_count` in favor of `catalyzed_metabolite_count` / `catalyst_gene_count` (catalysis-arm-only counts; transport arm split off). The explorer's reads now `coalesce(retired, 0)` = 0 everywhere. Per user decision, the MCP row fields rename too (loud break at the MCP layer, matching KG names 1:1).

## Change summary

| Tool | Row/envelope field (old → new) | KG property read (old → new) |
|---|---|---|
| `gene_overview` | row `metabolite_count` → `catalyzed_metabolite_count` | `g.metabolite_count` → `g.catalyzed_metabolite_count` |
| `list_organisms` | row `metabolite_count` → `catalyzed_metabolite_count`; `by_metabolic_capability[].metabolite_count` → `catalyzed_metabolite_count` | `o.metabolite_count` → `o.catalyzed_metabolite_count` (2 query sites) |
| `list_metabolites` | row `gene_count` → `catalyst_gene_count` | `m.gene_count` → `m.catalyst_gene_count` (2 query sites + `ORDER BY` tiebreaker) |

No parameter changes. No new fields (transport-arm row fields `transported_metabolite_count` / `transporter_gene_count` are slice-2 scope). No result-size-control changes.

## Per-layer touch points (verified by grep 2026-08-19)

- **`kg/queries_lib.py`**: `gene_overview` detail (L593); `list_organisms` detail (L1866) + capability query (L1964) + docstrings (L1813/1936/1945); `list_metabolites` detail (L1485/1509) + `ORDER BY m.gene_count` tiebreaker (L1520).
- **`api/functions.py`**: `list_organisms` `by_metabolic_capability` assembly (L955–966: dict key, zero-chemistry filter, sort key) + docstring (L886).
- **`mcp_server/tools.py`**: `GeneOverviewRow.metabolite_count` (L1875, description rewritten — the "reaction OR transport (UNION)" claim is dead); `OrganismResult` row + `OrgMetabolicCapabilityBreakdown` fields (~L1486–1565, envelope description updated); `MetaboliteResult.gene_count` (L409, description rewritten — see semantic trap below).
- **`inputs/tools/*.yaml`**: `gene_overview.yaml` example L52 (shows retired union value 554 — regenerate from live: PMM0392 now `catalyzed_metabolite_count: 0`); `list_organisms.yaml` examples L22/32/50/56 + chaining L70 + note L89; `list_metabolites.yaml` chaining L64 + mistakes L72/78–79 (rewrite, see trap).

**Semantic trap (must land in descriptions + mistakes):** the old guidance "`gene_count = 0` ⇒ metabolomics-only metabolite" is **false** after the split — a transport-only metabolite also has `catalyst_gene_count = 0`. Correct discriminator: `evidence_sources` (a `['metabolomics']`-only list means no gene path) or `transporter_count > 0`. Same logic for `gene_overview`: a transport-only gene has `catalyzed_metabolite_count = 0` with `transporter_count > 0` and `'transport' ∈ evidence_sources`.

**Explicitly untouched (audited, different concepts):** `Publication.metabolite_count` / `Experiment.metabolite_count` / `measured_metabolite_count` (metabolomics *measured* counts); `MetaboliteAssay.total_metabolite_count`; KEGG-pathway `p.metabolite_count`; ontology-node `gene_count` ("genes annotated to me"); `OrganismTaxon.gene_count`; computed `metabolite_count`/`gene_count` keys inside `genes_by_metabolite`/`metabolites_by_gene` envelope rollups (traversal-computed, not node-prop reads; their semantics are slice-2 scope); `gene_overview`'s `transporter_count` (aliases `g.tcdb_family_count`, untouched); traversal-computed `evidence_sources` / `has_chemistry` (verified not node-prop-dependent).

## Verified against live KG (2026-08-19, post-KG-SYNC-001 rebuild)

- `Gene {locus_tag:'PMM0392'}` → `catalyzed_metabolite_count: 0`, `transported_metabolite_count: 13`, `tcdb_family_count: 8`; retired `g.metabolite_count` absent (schema warning fires).
- `OrganismTaxon {preferred_name:'Prochlorococcus MED4'}` → `catalyzed_metabolite_count: 1039`, `reaction_count: 943`; retired prop absent.
- `Metabolite.catalyst_gene_count` populated on 2,225 metabolites (max 10,052 cross-organism); KG-side §8: 3,356 metabolites carry the property, 124,751 genes, 42 organisms.
- KG guard test `test_retired_catalysis_arm_names_are_absent` (KG repo) keeps the old names retired.

## Tests & docs

- Unit: column-name assertions in `test_query_builders.py` / `test_api_functions.py` / `test_tool_wrappers.py` for the 3 tools follow the rename (RED first). No `EXPECTED_TOOLS` / `TOOL_BUILDERS` changes (no tool added/removed). Edge-case scenarios: existing scenarios for these 3 tools updated only where they assert the renamed field names; no new fixtures needed.
- Regression: renamed columns ⇒ `pytest tests/regression/ --force-regen -m kg -q` per skill Stage 3.5, **restricted to the goldens of these 3 tools**; the repo-wide drift regen is the flanking task T5 (slice-1 plan) and happens in the same branch after Phase 2.
- Docs: YAML edits above + `build_about_content.py` regen + `--lint`; CLAUDE.md table rows for the 3 tools; explorer `CHANGELOG.md` [Unreleased] Breaking entries for the 3 MCP field renames (cite KG-SYNC-001).

## Acceptance

1. All 3 tools return the new field names with catalysis-only values; old field names absent from rows, envelopes, and docs.
2. No remaining read of `g.metabolite_count` / `o.metabolite_count` / `m.gene_count` anywhere in `kg/queries_lib.py` (label-scoped — the untouched list above stays).
3. Descriptions/mistakes teach the new discriminator (`evidence_sources` / `transporter_count`), not the dead union semantics.
4. Unit suite green; the 3 tools' regression goldens regen'd and green against the live KG.
