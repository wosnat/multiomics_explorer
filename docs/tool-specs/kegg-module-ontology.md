# Tool spec: `kegg_module` ontology + bridged walk-down fix (Mode B)

**Date:** 2026-11-19
**KG change:** `multiomics_biocypher_kg/docs/kg-changes/kegg-modules.md`; design + explorer
review in `multiomics_biocypher_kg/docs/superpowers/specs/2026-11-18-kegg-modules-design.md`
§10–§13.
**Mode:** B — cross-tool, registry-driven. No new tool. New optional parameter
`module_type` (third ontology facet, kegg_module only) on the six ontology tools; new
sparse response fields `module_type` (term, gene and enrichment rows) and `kegg_release`
(kg_release_info). Build A of two; Build B (`kegg_module_completeness` + rollups) is a
separate spec.

## Purpose

Surface KEGG modules (`KeggModule`, 414 modules + 57 `ko00002` class nodes) as the 18th
ontology, so modules can be searched, browsed, used as gene sets, and run through
enrichment. Modules are small functional units ("assimilatory nitrate reduction"), much
better ORA units than KEGG pathway maps. Same shape as BRITE: genes reach a module
through their KO (`Gene -[Gene_has_kegg_ko]-> KeggTerm -[Kegg_term_in_kegg_module]->
KeggModule`), and the class tree above modules is `Kegg_module_is_a_kegg_module`.

Also fixes backlog **2d.10**: in `term_ids` (walk-down) mode, a bridged ontology's gene
join skips the bridge hop, so BRITE `term_ids` return no genes. `kegg_module` would
inherit the bug.

## Out of scope (Build B / later)

- `kegg_module_completeness` tool over `Organism_has_kegg_module` (rows = edges only;
  per-module `organisms_without_edge` in the envelope — decided 2026-11-19).
- `list_organisms.complete_module_count`; organism-scoped module status in
  `ontology_term_details`.
- Defaulting `module_type` to `pathway` anywhere in this build. `module_type=None` keeps
  both kinds (pooling them is valid, unlike InterPro strata); Build B's completeness tool
  defaults to `pathway`.
- `Kegg_term_in_kegg_module.steps` / `.component` exposure (KO → module edge props) —
  Build B reads them.

## Status / Prerequisites

- [x] KG changes landed (dev KG `built_at` 2026-11-18T22:37:52Z, absorbed 4f6774c7)
- [x] Scope reviewed with user (two builds; envelope-only no-edge listing for B; module_type as an optional facet incl. enrichment)
- [x] Spec frozen (2026-11-19; `module_type` facet added on review)
- [x] Ready for Phase 2

## Tools affected

| Tool | Effect |
|---|---|
| all six facet tools (`search_ontology`, `genes_by_ontology`, `gene_ontology_terms`, `ontology_landscape`, `pathway_enrichment`, `cluster_enrichment`) | new optional `module_type: 'pathway' \| 'signature' \| None`, valid only with `ontology='kegg_module'` (else ValueError, as `tree` / `interpro_type`); binds on `t` after the walk; `module_type` column on kegg_module rows. |
| `search_ontology` | `ontology='kegg_module'` searches `keggModuleFullText` / browses by `gene_count`; `level` 0–3; omitted `ontology` fans out over 18. |
| `ontology_term_details` | `kegg.module:*` ids route to `kegg_module`; parents / children over `Kegg_module_is_a_kegg_module`; compact adds `module_type`, `module_id`, `step_count`, `definition`, `complete_organism_count` (modules; sparse on class nodes); links_out: KO → module (`Kegg_term_in_kegg_module`, membership) on `kegg` KO terms, module → map (`Kegg_module_in_kegg_pathway`, membership) on modules. |
| `genes_by_ontology` | mode 1 (`term_ids`, module or class) walks down through the bridge (2d.10 fix); mode 2 (`level`) rolls up; mode 3 scoped rollup; KEGG trust filters (bind on `Gene_has_kegg_ko`). |
| `gene_ontology_terms` | `ontology='kegg_module'` leaf = modules a gene's KO sits in; `mode='rollup'` to a class level. |
| `ontology_landscape` | default survey covers 18 ontologies; `kegg_module` contributes rows per (level, module_type) for levels 0–3 (facet in the grouping key, like `interpro_type`). |
| `pathway_enrichment` / `cluster_enrichment` | `ontology='kegg_module', level=3` = module ORA; class levels valid too. `module_type` optional (not required, unlike InterPro's `interpro_type`); rows carry `module_type`; envelope echoes the requested `module_type`. |
| `kg_release_info` | `kg.kegg_release` (str, sparse) from `Schema_info.kegg_release`. |
| BRITE via the same fix | `genes_by_ontology(ontology='brite', term_ids=[...])` and BRITE `term_ids`-scoped enrichment now return genes. |

## KG dependencies (verified against live KG 2026-11-19, built_at 2026-11-18T22:37:52Z)

| Object | Live value |
|---|---|
| `KeggModule` nodes | 471: level 0 `kegg_module_type` 2 · level 1 `kegg_module_class` 12 · level 2 `kegg_module_subclass` 43 · level 3 `kegg_module` 414 (382 pathway, 32 signature; 384 with genes) |
| props, all levels | `id, preferred_id, name, level, level_kind, module_type, gene_count, organism_count, complete_organism_count` |
| props, level 3 only | `module_id, definition, step_count, direct_gene_count` |
| absent | `description`, `is_uninformative` (none flagged — `informative_only` is a no-op) |
| ids | modules `kegg.module:M00531`; class slugs `kegg.module:pathway_modules.energy_metabolism.nitrogen_metabolism` |
| `Kegg_module_is_a_kegg_module` | module → subclass → class → type |
| `Kegg_term_in_kegg_module` | KO → module (level 3 only); props `steps`, `component` |
| `Kegg_module_in_kegg_pathway` | 1,254 edges, module → `KeggTerm` (`level_kind='pathway'`), 122 maps |
| indexes | `keggModuleFullText` (name), id / level / level_kind / module_id / module_type |
| `gene_count` | subtree via the KO bridge; recomputed bridge count == stored value on 471/471 nodes |
| `Schema_info.kegg_release` | `"pathway 2026-11-18, brite 2026-11-17, module 2026-11-09, ko …"` |

## Changes

### 1. Registry — `kg/queries_lib.py`

```python
"kegg_module": {
    "label": "KeggModule",
    "gene_rel": "Gene_has_kegg_ko",
    "hierarchy_rels": ["Kegg_module_is_a_kegg_module"],
    "fulltext_index": "keggModuleFullText",
    "bridge": {"node_label": "KeggTerm", "edge": "Kegg_term_in_kegg_module"},
    # binds `r` on Gene_has_kegg_ko, so it carries KEGG's trust axes (as BRITE)
    "trust": dict(_TRUST_SOURCES_EVIDENCE),
    # Third facet (after BRITE `tree`, InterPro `interpro_type`). Dense on
    # every level in the KG, so binding on `t` works at any level. The facet
    # machinery adds the `module_type` column to term / gene / landscape rows.
    "facet": {"prop": "module_type", "param": "module_type"},
    "term_compact": ["gene_count", "organism_count"],
    "term_details_compact": [
        "module_type", "module_id", "step_count", "definition",
        "direct_gene_count", "complete_organism_count",
    ],
    "term_details_verbose": "*",
    "bridges_out": [
        ("Kegg_module_in_kegg_pathway", "kegg", "membership"),
    ],
},
"kegg": {
    ...,
    "bridges_out": [
        ("Kegg_term_in_brite_category", "brite", "membership"),
        ("Kegg_term_in_kegg_module", "kegg_module", "membership"),   # new
    ],
},
```

Sparse rule (existing strip behaviour): level-3-only props are absent on class rows.

### 2. Key lists

- `kg/constants.py` `ALL_ONTOLOGIES`: **append** `"kegg_module"` (order is load-bearing for
  landscape fixtures). Header comment 17 → 18.
- `mcp_server/params.py` `OntologyKey`: add `"kegg_module"`.
- `scripts/build_about_content.py`: display name `"KEGG modules (module classes, modules)"`;
  `ONTOLOGY_LEVEL_RANGES["kegg_module"] = (0, 3)`; filter-type owner tuple if a
  `list_filter_values` type is owned (none expected — `module_type` is not a
  `list_filter_values` filter in this build).

### 3. 2d.10 fix — `_genes_by_ontology_match_stage` (term_ids mode)

The hierarchical branch emits `MATCH {gene}-[r:{gene_rel}]->(leaf)`. For an ontology with
`cfg["bridge"]` emit instead:

```cypher
MATCH {gene}-[r:{gene_rel}]->(:{bridge.node_label})-[:{bridge.edge}]->(leaf)
```

Trust / gate / organism predicates keep binding on `r`. Apply the same audit to every other
term_ids / walk-down head that joins genes to a `leaf` (enrichment TERM2GENE scoped by
`term_ids`, `ontology_term_details` `genes_by_organism`, landscape) — any head that lacks
the bridge hop for a bridged ontology is fixed the same way. Level mode (`bind_up`) and
`_search_ontology_org_scope` already cross the bridge.

### 3b. Facet plumbing — `module_type`

- `_FACET_PARAMS` is derived from the registry; `_resolve_facet` gains a `module_type`
  keyword next to `tree` / `interpro_type` (same validation: wrong ontology → ValueError).
- Every builder / api function / wrapper that threads `interpro_type` threads
  `module_type` the same way (template: `interpro_type`; 54 api / 33 wrapper sites).
  Difference: never required — `_check_enrichment_*` gains no `module_type` guard.
- Enrichment: TERM2GENE and the background are shaped by the same facet (as
  `interpro_type`); `analysis/enrichment.py` echoes `module_type` in the envelope and strips
  the sparse row column when absent (same NaN → None handling as `tree`).
- Validation: `module_type` ∈ {`pathway`, `signature`}
  (`ControlledVocabulary` `KeggModule.module_type`); Literal on the wrapper.

### 4. Response fields — `mcp_server/tools.py`

- `module_type` param on the six facet tools: `Literal['pathway', 'signature'] | None`,
  description "KEGG module type (kegg_module only): 'pathway' = routes, 'signature' =
  marker sets such as drug resistance. Default both."
- `module_type: str | None` sparse on every row model that carries `interpro_type` today
  (search_ontology, ontology_term_details, genes_by_ontology, gene_ontology_terms,
  ontology_landscape, pathway / cluster enrichment), description "KEGG module type:
  'pathway' (a route) or 'signature' (a marker set). kegg_module only."
- `ontology_term_details` row models also accept `module_id`, `step_count`, `definition`,
  `complete_organism_count` as sparse (kegg_module only; level-3 modules), each ≤ 250-char
  descriptions. `complete_organism_count` description says it counts organisms with a
  `complete` module edge, and differs from `organism_count` (KO-bridge genes).
- `kg_release_info`: `kegg_release: str | None` on the kg block; `api/functions.py` adds
  `"kegg_release"` to the Schema_info passthrough list.
- `ontology` parameter descriptions that enumerate the keys gain `kegg_module`.

### 5. Schema baseline — `config/schema_baseline.yaml` (hand-patched)

`KeggModule` label with the props above; rels `Kegg_module_is_a_kegg_module`,
`Kegg_term_in_kegg_module` (props `steps`, `component`), `Kegg_module_in_kegg_pathway`,
`Organism_has_kegg_module` (edge props per the KG note); `OrganismTaxon` assembly props;
`Schema_info.kegg_release`. Hand-patch, not `save_baseline()` (sampler drops sparse props).

### 6. Docs

| File | Change |
|---|---|
| `inputs/ontologies/kegg_module.yaml` (new) | `what_it_is`, `method` (KEGG module definitions; genes reach modules via KO; EC-only genes do not count in `gene_count`), `id_form` (real `M\d+` CURIEs vs house slugs), `hierarchy` (4 levels, `level_kind`), `interpretation` (gene set = genes with a KO in the module; completeness lives on the organism edge — Build B), `informativeness_rule` (none flagged; signature vs pathway via `module_type`), `pitfalls` (`organism_count` ≠ organisms with a module edge; signature modules are marker sets; a gene set is not a complete route), `typical_questions`, `see_also` (`docs://ontologies/kegg`, `docs://ontologies/brite`, `docs://analysis/enrichment`) |
| `inputs/ontologies/kegg.yaml` | see_also + one line: modules are a separate ontology, KO → module link |
| `inputs/tools/{search_ontology,genes_by_ontology,gene_ontology_terms,ontology_landscape,ontology_term_details,pathway_enrichment,cluster_enrichment}.yaml` | 17 → 18 sweep; add one kegg_module example each to search_ontology, genes_by_ontology (term_ids on a module — exercises the fix), pathway_enrichment (`level=3`) |
| `references/analysis/enrichment.md` | module ORA paragraph: `level=3`, why modules beat maps, signature modules |
| `references/guide/{concepts,conventions,start_here}.md`, `references/analysis/annotation_evidence.md` | 17 → 18; trust surface "16 of the 18" |
| `CLAUDE.md` | tool-table ontology counts 17 → 18 |
| `inputs/lint/kg_claims.yaml` | `'17 ontologies'` / `'all 17'` claims → 18 |
| `inputs/lint/stale_identifiers.yaml` | add `17 ontologies` → `18 ontologies (ONTOLOGY_CONFIG)` |
| `docs/backlog.md` | delete 2d.10 when shipped |

Regenerate: `uv run python scripts/build_about_content.py --live-vocab`; `--lint` gate.

### 7. Tests

| File | Change |
|---|---|
| `tests/unit/test_config_registry.py` | kegg_module row (label, gene_rel, bridge, hierarchy, trust), `EXPECTED_BRIDGES` for kegg + kegg_module |
| `tests/unit/test_query_builders.py` | bridged term_ids head contains the bridge hop for `brite` and `kegg_module` (2d.10 regression); kegg_module walk_up / walk_down / bind_up fragments |
| `tests/unit/test_tool_wrappers.py` | `module_type` param on the six facet tools; sparse row field; `kegg_release` on kg_release_info |
| `tests/unit/test_query_builders.py` (facet) | `module_type='signature'` binds `t.module_type = $module_type`; `module_type` with a non-kegg_module ontology raises; landscape grouping key carries `module_type` |
| `tests/unit/test_api_functions.py` (enrichment) | `module_type` reaches TERM2GENE + background; envelope echo; no requirement guard |
| `tests/unit/*` fan-out counts | `len(ALL_ONTOLOGIES) == 18`-style assertions updated where they pin 17 (ADD, don't loosen) |
| `tests/integration` (kg) | MED4 `genes_by_ontology(kegg_module, level=3)` = 386 genes / 205 modules; `term_ids=['kegg.module:M00531']` WH8102 = SYNW2464, SYNW2477 (also via the subclass id); BRITE `kegg.brite:ko02000.A1.B2` MED4 term_ids = 6 genes (2d.10); `search_ontology('nitrate', kegg_module)` top hits M00530/M00531; `ontology_term_details(['kegg.module:M00531'])` parents = subclass, links_out to maps; `test_none_fans_out_to_all_17` → 18 |
| `tests/evals/cases.yaml` | one kegg_module case per affected tool family (search, genes_by_ontology term_ids, enrichment level 3) |
| goldens | `ontology_landscape_med4_all*` gain kegg_module rows (appended); `--force-regen` only those + any brite term_ids case |
| edge-case scenarios | no new tool → coverage gate unaffected; add a kegg_module degenerate case (class id with zero genes in an organism) if `genes_by_ontology` scenarios enumerate ontologies |

### 8. Verified Cypher (live KG, built_at 2026-11-18T22:37:52Z)

```cypher
-- mode-2 rollup, MED4: 386 genes at every level; 2 / 11 / 34 / 205 terms at levels 0-3
MATCH (g:Gene {organism_name:'Prochlorococcus MED4'})-[:Gene_has_kegg_ko]->(:KeggTerm)
      -[:Kegg_term_in_kegg_module]->(leaf:KeggModule)-[:Kegg_module_is_a_kegg_module*0..]->(t:KeggModule)
RETURN t.level, count(DISTINCT t), count(DISTINCT g)

-- mode-1 walk-down WITH the bridge hop: M00531 and its subclass both -> SYNW2464, SYNW2477 (WH8102)
UNWIND ['kegg.module:M00531','kegg.module:pathway_modules.energy_metabolism.nitrogen_metabolism'] AS input_tid
MATCH (t:KeggModule {id: input_tid})<-[:Kegg_module_is_a_kegg_module*0..]-(leaf:KeggModule)
MATCH (g:Gene {organism_name:'Synechococcus WH8102'})-[r:Gene_has_kegg_ko]->(:KeggTerm)-[:Kegg_term_in_kegg_module]->(leaf)
RETURN input_tid, count(DISTINCT g)

-- 2d.10: BRITE kegg.brite:ko02000.A1.B2, MED4 — current head 0 genes, with bridge hop 6
-- gene_count: bridge recount == KeggModule.gene_count on 471/471 nodes
-- fulltext keggModuleFullText 'nitrate' -> M00530, M00531, M00615, M00529, M00804
-- Kegg_module_in_kegg_pathway: 1,254 edges, all to level_kind='pathway'
-- module_type dense on all 471 nodes (pathway: 1 type / 10 classes / 40 subclasses / 382 modules;
--   signature: 1 / 2 / 3 / 32), so the facet binds on t at any level
-- facet at level 3, MED4: pathway 203 modules / 381 genes; signature 2 modules / 5 genes
```

## Gate

Frozen after user approval. Adding fields / params / builder changes bumps back to Phase 1.
