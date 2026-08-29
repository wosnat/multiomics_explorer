# Tool spec: TIGR-role hierarchy + NCBIfam→TigrRole bridge absorb (Mode B)

**Date:** 2026-08-29
**KG change:** `multiomics_biocypher_kg/docs/kg-changes/tigr-role-bridge.md`
**Mode:** B — cross-tool small change, registry-driven. No new tool, no new
parameter, no new response field.

## Purpose

Absorb the 2026-08-29 KG rebuild in which `TigrRole` became a two-level
ontology (subrole → mainrole, `Tigr_role_is_a_tigr_role`), gained an
`NcbifamFamily → TigrRole` bridge (`Ncbifam_family_has_tigr_role`), and
`Gene_has_tigr_role` widened to all 43 organisms with two evidence rungs
(`curated` / `family_inferred`; `sources` ⊆ `[cyanorak, interproscan]`).

The explorer encodes the old flat / Cyanorak-only shape in one registry row
and five doc surfaces. This spec corrects them.

## Out of scope

- An "annotated-genes" ORA background mode for `pathway_enrichment` /
  `cluster_enrichment` (the KG doc's recommended TIGR background). Workaround:
  explicit `background=` list from `genes_by_ontology(ontology='tigr_role',
  level=0)`. → `docs/backlog.md`.
- Any new exposure of `Gene_has_tigr_role.sources` / `.evidence` — the
  existing `[TRUST]` filters (`sources`, `evidence`) read them live and
  already use membership (`any(s IN $sources WHERE s IN r.sources)`).
- KG-side doc fixes (4 items) — passed back as a prompt; doc-only, no rebuild.

## Status / Prerequisites

- [x] KG changes landed (live KG `built_at` 2026-08-29T10:11Z, verified)
- [x] Scope reviewed with user (Q1 link_kind=`router`, Q3 no size-control change)
- [x] Spec frozen (2026-08-29)
- [x] Ready for Phase 2

## Tools affected

| Tool | Effect of the registry change |
|---|---|
| `search_ontology` | browse mode `by_level` now 2 buckets for tigr_role; `level=1` returns subroles; verbose `level_kind` / `direct_gene_count` populated |
| `genes_by_ontology` | mode 2 (`level=0`) rolls subroles up to mainroles; mode 3 scoped rollup works; `level=1` no longer empty |
| `gene_ontology_terms` | `rollup` mode (target level 0) works for tigr_role |
| `ontology_landscape` | tigr_role contributes 2 rows (L0, L1), `n_levels=2` |
| `ontology_term_details` | `parents[]` / `children[]` over `Tigr_role_is_a_tigr_role`; compact gains `direct_gene_count`, `ncbifam_family_count`; ncbifam terms gain `links_out` rows `{rel: Ncbifam_family_has_tigr_role, link_kind: router, target_ontology: tigr_role}` |
| `pathway_enrichment` / `cluster_enrichment` | `ontology='tigr_role', level=0` is a valid mainrole-level ORA |
| `gene_overview` (no code change) | `by_annotation_type.tigr_role` and `by_category` shift on non-Cyanorak organisms (KG-side fill); goldens only |

## KG dependencies (verified against live KG 2026-08-29)

| Object | Live value |
|---|---|
| `TigrRole` nodes | 136 = 21 `level=0` (`level_kind='tigr_mainrole'`; 19 slug ids + numeric roots `270`, `856`) + 115 `level=1` (`tigr_subrole`) |
| `TigrRole` props | `code, direct_gene_count, gene_count, id, level, level_kind, name, ncbifam_family_count, organism_count, preferred_id` |
| `Tigr_role_is_a_tigr_role` | 115 (one parent per subrole) |
| `Ncbifam_family_has_tigr_role` | 1,847, no properties, all targets are subroles; 159 families carry >1 role |
| `Gene_has_tigr_role` | 65,513 across 43 organisms; `evidence` ∈ {curated 49,213 (of which 9,669 merged `[cyanorak, interproscan]`), family_inferred 16,300} |
| uninformative TigrRole | `156, 157, 185, 270, 704, 856, hypothetical_proteins, unclassified, unknown_function` |
| `ControlledVocabulary` | `Gene_has_tigr_role.sources` / `.evidence` closed, with `value_descriptions` |

## Changes

### 1. Registry — `kg/queries_lib.py`

```python
"tigr_role": {
    ...
    "hierarchy_rels": ["Tigr_role_is_a_tigr_role"],          # was []
    "term_details_compact": ["code", "direct_gene_count", "ncbifam_family_count"],  # was ["code"]
},
"ncbifam": {
    ...
    "bridges_out": [
        ("Ncbifam_family_in_interpro_entry", "interpro", "membership"),
        ("Ncbifam_family_has_tigr_role", "tigr_role", "router"),   # new
    ],
},
```

`router` (not `composition`): read outward only — the bridge suggests a role
for a family; the KG asserts a *gene* role from it solely for `equivalog`
families. Same contract as `Interpro_entry_related_to_ec_number`.

No builder code changes: `_hierarchy_walk`, browse `by_level`, landscape
per-level, term-details parents/children/links_out and enrichment TERM2GENE
are all registry-driven (the CyanorakRole row is the working precedent).

### 2. Schema baseline — `config/schema_baseline.yaml` (hand-patched)

- `TigrRole.properties` += `direct_gene_count: int`, `level_kind: string`,
  `ncbifam_family_count: int`
- new rels `Tigr_role_is_a_tigr_role` (TigrRole→TigrRole),
  `Ncbifam_family_has_tigr_role` (NcbifamFamily→TigrRole), `properties: {id}`
- `ControlledVocabulary.properties` += `value_descriptions: list` (rebuild #4
  leftover, real)

Hand-patch, not `save_baseline()` — the sampler drops sparse props
(`OrganismTaxon.name_synonyms` 2/48, `Derived_metric_quantifies_gene.
metric_bucket` 22,302/22,985) and would regress the file.

### 3. Docs

| File | Change |
|---|---|
| `inputs/ontologies/tigr_role.yaml` | rewrite `method` (two sources, evidence ladder, `IN r.sources`), `hierarchy` (2 levels, slug vs numeric ids, `level_kind` is the discriminator, subtree `gene_count` on mainroles), `interpretation` (cross-genus comparable), `pitfalls` (drop "flat"; add coverage-bias ORA background; `level=0` now returns 21 roots; mainrole `code` is a slug), `typical_questions` (+heterotroph-by-role), `see_also` (+ `docs://ontologies/ncbifam`) |
| `inputs/tools/genes_by_ontology.yaml:212` | flat list → `cog_category` only |
| `inputs/tools/search_ontology.yaml:263` | remove TIGR from flat list; note TIGR L0 = mainroles |
| `inputs/tools/ontology_landscape.yaml:9,24,132` | examples `n_levels: 2`, `best_level` per live; mistakes line drops tigr_role from flat examples |
| `references/analysis/annotation_evidence.md` | `tigr_role` row: note `sources ⊆ [cyanorak, interproscan]`, `evidence ∈ {curated, family_inferred}`, membership filter |
| `references/analysis/enrichment.md:510` | unchanged (TIGR is a tree — now true) |
| `CLAUDE.md` | `ontology_term_details` prefix list + `tigr.role:…`; `search_ontology` row: TIGR no longer flat |
| `docs/backlog.md` | + "annotated-genes ORA background mode" (S, origin: tigr-role-bridge) |

Regenerate via `uv run python scripts/build_about_content.py`; `--lint` gate.

### 4. Tests

| File | Change |
|---|---|
| `tests/unit/test_query_builders.py::test_tigr_role_flat` | → `test_tigr_role_two_level`: `Tigr_role_is_a_tigr_role` in `walk_up` |
| `tests/unit/test_config_registry.py::EXPECTED_BRIDGES["ncbifam"]` | + router tuple |
| `tests/unit/test_config_registry.py` | + `test_tigr_role_term_details_compact` |
| `tests/unit/test_about_content.py` | passes once yaml + md regenerated (asserts hierarchy rel appears in md) |
| `tests/unit/test_api_functions.py:5475-5515` | mock-based landscape test; leave (mock data, not KG) |
| goldens (`--force-regen -m kg`) | `search_ontology_tigr_role`, `gene_ontology_terms_tigr_role`, `ontology_landscape_med4_all`, `ontology_landscape_med4_all_no_filter`, + any `gene_overview_*` / `gene_details_*` that move from the KG-side category fill / `annotation_types` |
| edge-case scenarios | none new (no new tool); coverage gate unaffected |
| `tests/integration/test_mcp_tools.py::TestOntologyLandscapeIntegration` (found in VERIFY) | `test_med4_all_ontologies_cyanorak_l1_rank1_among_hierarchical` → `..._tigr_l1_rank1_...`: tigr_role L1 (MED4 coverage 0.62) now outranks cyanorak_role L1 (0.56) among hierarchical rows; cyanorak L1 still asserted present |
| `kg/constants.py` `EXPECTED_CONTROLLED_VOCABULARIES_HASH` (found in VERIFY) | re-pinned to the 2026-08-29T10:11Z build (`sha256:a7c97e00…`) — vocabulary genuinely changed (`TigrRole.level_kind`, widened `Gene_has_tigr_role.sources`/`.evidence`); same practice as 6a4b18a |
| goldens actually regenerated | the 4 TIGR cases + 14 KG-side movers (11 `genes_by_function_*` via `[tigr_role_inferred]` full-text lines, 2 `list_filter_values*` via the `gene_category` fill, `gene_details_synechococcus`) |
| `tests/unit/test_query_builders.py` (found in GREEN) | 4 pre-existing tests used `tigr_role` as the *flat-ontology exemplar* (`test_flat_ontology_mode2`, 2× `test_flat_ontology_omits_hierarchy_walk`, `test_verbose_no_direct_gene_count_on_flat_label[tigr_role]`); re-pointed to `cog_category`, assertions unchanged |

### 5. Verified Cypher (live KG 2026-08-29)

```cypher
-- mode-2 rollup: MED4 leaf gene set == L0 rollup gene set (1,766 genes; 107 leaf terms → 21 L0 terms)
MATCH (g:Gene {organism_name:'Prochlorococcus MED4'})-[:Gene_has_tigr_role]->(leaf:TigrRole)
      -[:Tigr_role_is_a_tigr_role*0..1]->(t:TigrRole) WHERE t.level=0
RETURN count(DISTINCT g), count(DISTINCT t)

-- mode-1 expand-down from a mainrole on a heterotroph: 100 HOT1A3 genes, 13 subroles, all family_inferred
MATCH (root:TigrRole {id:'tigr.role:energy_metabolism'})<-[:Tigr_role_is_a_tigr_role*0..1]-(t)
      <-[r:Gene_has_tigr_role]-(g:Gene {organism_name:'Alteromonas macleodii HOT1A3'})
RETURN count(DISTINCT g), count(DISTINCT t), collect(DISTINCT r.evidence)

-- term details: tigr.role:164 parents=[energy_metabolism] children=0; energy_metabolism children=16 direct=0 subtree=7353
-- bridge fan-out: ncbifam:TIGR00202 (equivalog) → [tigr.role:116, tigr.role:262]
-- trust filter membership: MED4 484 edges carry 'interproscan', 422 of them merged (evidence='curated')
```

## Gate

Frozen after user approval. Adding fields / params / builder changes bumps
back to Phase 1.
