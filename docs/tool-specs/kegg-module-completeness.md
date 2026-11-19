# Tool spec: `kegg_module_completeness` + module rollups (Mode A + 3 small extensions)

**Date:** 2026-11-19
**KG change:** `multiomics_biocypher_kg/docs/kg-changes/kegg-modules.md`; design + explorer
review in `multiomics_biocypher_kg/docs/superpowers/specs/2026-11-18-kegg-modules-design.md`
§4–§5, §10–§13.
**Mode:** A (one new tool, KG iteration done) plus three small extensions to existing tools
(`list_organisms`, `ontology_term_details`, `list_filter_values`). Build B of two; Build A
(`kegg_module` ontology, `a858de05`) is `docs/tool-specs/kegg-module-ontology.md`.

## Purpose

Answer "which KEGG modules can this strain run, and what is it missing?" and "which strains
carry module X complete?" from the KG's precomputed `Organism_has_kegg_module` edges (KEGG
Mapper bands, EC fallback). Build A made modules usable as gene sets; this build makes the
organism-level completeness call usable, with the missing steps / KOs that say what to look
for next.

## Out of scope

- Synthetic `absent` rows. Rows are edges only; strains with no edge are reported in the
  envelope as `no_edge` counts (`by_class`, `top_organisms`, `top_modules`, `no_edge_count`) and, for ≤ 3 modules, `top_modules[*].organisms_without_edge`
  — user decision 2026-11-19.
- Gene-level evidence per step (which locus tag covers step 3). KO-covered steps are a join
  through `genes_by_ontology(ontology='kegg_module', term_ids=[module])`; only EC-only genes
  are on the edge (`ec_genes`, verbose). A per-step gene view is a later item if asked.
- `Kegg_term_in_kegg_module.steps` / `.component` exposure.
- Class-level organism rollups in `ontology_term_details` (e.g. complete modules under a
  class for one organism) — level-3 module rows only.
- `best_module_type` in `ontology_landscape` (Build A review follow-up; separate).

## Status / Prerequisites

- [x] KG changes landed (dev KG built 2026-11-18T22:37:52Z, absorbed `4f6774c7`)
- [x] Scope reviewed with user (rows = edges only; envelope-only absence; default `module_type='pathway'`)
- [x] Spec frozen (2026-11-19)
- [x] Ready for Phase 2

## Use cases

- **Strain capability:** "what can MED4 make / degrade?" →
  `kegg_module_completeness(organism='Prochlorococcus MED4', status=['complete'])`, read
  `by_class`.
- **Near-misses (annotation gap vs real loss):** `status=['one_step_missing']` → `missing_kos`
  → `genes_by_function` / `resolve_gene` / `gene_ontology_terms` to look for an unannotated
  candidate.
- **Cross-strain distribution of a module:** `kegg_module_completeness(module_ids=['M00531'])`
  → per-strain status + `top_modules[0].organisms_without_edge`. Example (live): nitrate
  assimilation M00531 is complete in 56 genomes, one step missing in 26, no edge in 36 —
  incl. MED4 (no nitrate / nitrite reductase); MIT9313 has nitrite reductase only
  (`one_step_missing`, missing nitrate reductase KOs).
- **Class sweep:** `module_ids=['kegg.module:pathway_modules.energy_metabolism.nitrogen_metabolism']`
  — a class / subclass id expands to its modules.

Chains: `list_organisms` (`complete_pathway_module_count`) → `kegg_module_completeness` →
`genes_by_ontology(ontology='kegg_module', term_ids=[...], organism=...)` for the KO-covered
genes; `search_ontology(ontology='kegg_module')` → module ids → here;
`ontology_term_details(term_ids=[module], organism=X)` → one organism's status on one module.

## KG dependencies (verified against live KG 2026-11-19, built_at 2026-11-18T22:37:52Z)

- `(:OrganismTaxon)-[:Organism_has_kegg_module]->(:KeggModule {level: 3})` — 26,004 edges,
  118 organisms (every organism with genes), 414 modules (367 pathway with an edge).
  Edge props: `status` (CV `Organism_has_kegg_module.status`: `complete`,
  `one_step_missing`, `two_steps_missing`, `partial`), `steps_total`, `steps_present`,
  `steps_present_via_ec`, `missing_step_indices` int[], `missing_step_definitions` str[],
  `missing_kos` str[] (bare `K#####`; never null; max 32, mean 3.3), sparse
  `ec_filled_step_indices` int[] / `ec_genes` str[] (null on 22,819 edges; parallel; a slot
  may hold a module id `M#####` for a module-reference step).
- Status × module_type: pathway complete 6,700 / one_step 5,550 / two_steps 4,093 /
  partial 8,220; signature 285 / 314 / 695 / 147.
- `KeggModule`: levels 0 type / 1 class / 2 subclass / 3 module; `module_type` dense on all
  levels; every module has exactly one `module → subclass → class` chain
  (`Kegg_module_is_a_kegg_module`, 414/414). Module props `module_id`, `step_count`,
  `definition`, `organism_count` (KO bridge), `complete_organism_count` (edges).
- Ids: modules `kegg.module:M00531`; class nodes are house slugs
  (`kegg.module:pathway_modules.energy_metabolism.nitrogen_metabolism`).
- **No edge ≠ no genes.** No edge = no step covered. A one-step complex module with one
  subunit unannotated has no edge: Synechococcus elongatus PCC 7942 carries 5 / 6 PSII
  (M00161) subunit KOs, but `psbD` (K02706) has no KO, so the single `+` step is uncovered and
  there is no edge. Docs must say this.

No KG change needed.

---

## Tool signature

```python
@mcp.tool(tags={"kegg", "modules", "organism", "metabolism"},
          annotations={"readOnlyHint": True})
async def kegg_module_completeness(
    ctx: Context,
    organism: str | list[str] | None = None,   # same semantics as genes_by_ontology
    module_ids: list[str] | None = None,       # modules or class / subclass / type ids; bare 'M00531' ok
    status: list[Literal['complete','one_step_missing','two_steps_missing','partial']] | None = None,
    module_type: Literal['pathway','signature'] | None = 'pathway',   # None = both
    summary: bool = False,
    verbose: bool = False,
    limit: int = 50,   # ge=0? follow genes_by_ontology convention
    offset: int = 0,
) -> KeggModuleCompletenessResponse:
```

Docstring (draft): "Report how complete each KEGG module is in each organism — KEGG Mapper
bands over the module's steps, KO evidence plus an EC fallback. One row per (organism,
module) that has at least one step covered; strains with no covered step are listed in the
envelope, not as rows. `complete` means every step has an annotated gene, not that the route
runs. Routing: `missing_kos` → `genes_by_function` / `resolve_gene` to look for an
unannotated candidate; `genes_by_ontology(ontology='kegg_module', term_ids=[module_id],
organism=...)` for the genes behind KO-covered steps."

### Parameters

| Param | Semantics |
|---|---|
| `organism` | Reuse `_gbo_resolve_organism_scope`: `str` = exactly one organism (raises on ambiguous, suggests a list), `list` = word-matched union (unmatched → `not_found_organisms`; empty list raises), `None` = every organism with genes. |
| `module_ids` | KeggModule ids at any level. Level 3 = that module; level 0–2 = every module under it. Bare `M\d{5}` → `kegg.module:M\d{5}`. Unknown → `not_found_modules`. Known but every module it yields is excluded by `module_type` → `not_matched_modules` + a warning naming the fix (`module_type='signature'` or `None`). Empty list raises. |
| `status` | Subset of the four bands; validated against CV `Organism_has_kegg_module.status` (pivot fallback + warning, per conventions); unknown raises `ValueError` listing the allowed set. Filters rows and the status-based rollups, never the absence lists. |
| `module_type` | Default `'pathway'`; `'signature'`; `None` keeps both. Validated against CV `KeggModule.module_type`. |
| `summary` / `verbose` / `limit` / `offset` | Standard. `summary=True` ≡ `limit=0`. |

### Rows (`KeggModuleCompletenessRow`, `SparseRow`)

Sort: `module_id` ASC, status band (complete → one_step_missing → two_steps_missing →
partial), `organism_name` ASC. Groups a module's strains together, complete first; a
single-organism call reads in KEGG module order.

| Field | Type | Compact / verbose | Description |
|---|---|---|---|
| `organism_name` | str | compact | e.g. `'Prochlorococcus MIT9313'` |
| `module_id` | str | compact | e.g. `'kegg.module:M00531'` |
| `module_name` | str | compact | e.g. `'Assimilatory nitrate reduction, nitrate => ammonia'` |
| `module_type` | str | compact | `pathway` \| `signature` |
| `module_class` | str | compact | level-1 class name, e.g. `'Energy metabolism'` |
| `status` | str | compact | band; `complete` = every step has an annotated gene (KO or EC fallback), not shown to run |
| `steps_total` | int | compact | module step count (`--` steps excluded) |
| `steps_present` | int | compact | steps covered, KO or EC |
| `steps_present_via_ec` | int | compact | of those, covered only through EC; KO-only count = `steps_present - steps_present_via_ec` |
| `missing_step_indices` | list[int] | compact | 1-based, `[]` when complete |
| `missing_kos` | list[str] | compact | every KO named in the missing steps, flattened; one KO from it may not complete a step (a `+` complex needs all subunits); a missing module-reference step contributes none. e.g. `['K00367','K00372','K10534']` |
| `module_subclass` | str | verbose | level-2 subclass name, e.g. `'Nitrogen metabolism'` |
| `definition` | str | verbose | module KO formula (same grammar text as Build A's `definition`) |
| `missing_step_definitions` | list[str] | verbose | formula of each missing step, parallel to `missing_step_indices`, e.g. `['(K00367,K10534,K00372+K00360)']` |
| `ec_filled_step_indices` | list[int] | verbose | steps covered only through EC; `[]` when none (KG null coalesced) |
| `ec_genes` | list[str] | verbose | locus tag filling each EC step, parallel to `ec_filled_step_indices`; a module id (`M#####`) in a slot = a module-reference step completed via EC; `[]` when none |

Missing KOs are bare `K#####` as stored (not `kegg.orthology:`-prefixed); the description
says so and names `kegg.orthology:{ko}` for chaining into `ontology_term_details` /
`genes_by_ontology(ontology='kegg', ...)`.

### Envelope (`KeggModuleCompletenessResponse`)

| Key | Type | Meaning |
|---|---|---|
| `total_entries` | int | all `Organism_has_kegg_module` edges in the KG |
| `total_matching` | int | rows matching every filter |
| `returned`, `truncated`, `offset` | | standard |
| `organism_name` | str \| None | the organism when exactly one is in scope, else None |
| `organisms_in_scope` | int | organisms the call covers (after resolution) |
| `modules_in_scope` | int | level-3 modules the call covers (after `module_ids` expansion and `module_type`) |
| `by_status` | list[{status, count}] | four bands always present, band order, counts after filters |
| `no_edge_count` | int | (organism, module) pairs in scope with no edge = `organisms_in_scope × modules_in_scope − pairs with an edge`; independent of `status` |
| `by_class` | list[{class_id, class_name, module_count, complete, one_step_missing, two_steps_missing, partial, no_edge}] | complete breakdown (≤ 12 classes): per level-1 class with ≥1 module in scope; `module_count` = modules in scope under the class; status counts after filters; `no_edge` = (organism, module) pairs under the class with no edge. Sort `class_id`. |
| `top_organisms` | list[{organism_name, complete, one_step_missing, two_steps_missing, partial, no_edge}] | **capped at 20**; organisms in scope (incl. all-zero), sorted `complete` DESC, `organism_name`; status counts after filters; `no_edge` = modules in scope with no edge for that organism (independent of `status`). Compare length with `organisms_in_scope`. |
| `top_modules` | list[{module_id, module_name, module_type, complete, one_step_missing, two_steps_missing, partial, no_edge, organisms_without_edge?}] | **capped at 20**; modules in scope, sorted `complete` DESC, `module_id`; `no_edge` = organisms in scope with no edge to the module (independent of `status`). `organisms_without_edge` (sorted names) present on each entry only when `modules_in_scope ≤ 3`, absent otherwise. Compare length with `modules_in_scope`. |

**Size rule:** the envelope is bounded by the cap, not by the KG — worst case (all 118
organisms × 367 pathway modules) is 4 + ≤12 + 20 + 20 entries; names of organisms without an
edge appear only for ≤ 3 modules (≤ ~350 names). Whole-axis tables come from paging rows.
An explicit `organism` / `module_ids` list of ≤ 20 shows every entry.
| `not_found_modules` | list[str] | input ids with no KeggModule node |
| `not_matched_modules` | list[str] | input ids that exist but yield no module under `module_type` |
| `not_found_organisms` | list[str] | list entries matching no organism |
| `warnings` | list[str] | |

Zero-row outcomes are distinct: `not_found_*` (input unknown), `not_matched_modules`
(filtered by `module_type`), no row but `organisms_without_edge` (module known, no step
covered in that strain), rows filtered by `status` (counts in `by_status` drop, absence
lists unchanged).

## Query builders (`kg/queries_lib.py`)

Shared WHERE (`_kmc_where`), params `$organisms` (list of canonical names or null),
`$module_ids` (normalised list or null), `$module_type` (str or null), `$status` (list or
null):

```cypher
WHERE ($organisms IS NULL OR o.preferred_name IN $organisms)
  AND ($module_type IS NULL OR m.module_type = $module_type)
  AND ($module_ids IS NULL OR EXISTS {
        MATCH (m)-[:Kegg_module_is_a_kegg_module*0..3]->(a:KeggModule)
        WHERE a.id IN $module_ids })
  AND ($status IS NULL OR r.status IN $status)
```

For `organism=None` the api passes `$organisms = null` (edges exist only on organisms with
genes, verified 118 = 118).

### `build_kegg_module_completeness` (detail) — verified against live KG

```cypher
MATCH (o:OrganismTaxon)-[r:Organism_has_kegg_module]->(m:KeggModule {level: 3})
<_kmc_where>
MATCH (m)-[:Kegg_module_is_a_kegg_module]->(sub:KeggModule)
      -[:Kegg_module_is_a_kegg_module]->(cls:KeggModule)
WITH o, r, m, sub, cls,
     CASE r.status WHEN 'complete' THEN 0 WHEN 'one_step_missing' THEN 1
                   WHEN 'two_steps_missing' THEN 2 ELSE 3 END AS status_rank
RETURN o.preferred_name AS organism_name, m.id AS module_id, m.name AS module_name,
       m.module_type AS module_type, cls.name AS module_class, r.status AS status,
       r.steps_total AS steps_total, r.steps_present AS steps_present,
       r.steps_present_via_ec AS steps_present_via_ec,
       r.missing_step_indices AS missing_step_indices, r.missing_kos AS missing_kos
       -- verbose:
       , sub.name AS module_subclass, m.definition AS definition,
       r.missing_step_definitions AS missing_step_definitions,
       coalesce(r.ec_filled_step_indices, []) AS ec_filled_step_indices,
       coalesce(r.ec_genes, []) AS ec_genes
ORDER BY module_id, status_rank, organism_name
SKIP $offset LIMIT $limit
```

Verified: MED4 + WH8102 + MIT9313 × nitrogen-metabolism subclass → 2 rows (M00531 WH8102
complete 2/2; MIT9313 one_step_missing 1/2, missing_kos `[K00367,K00372,K10534]`); HOT1A3
glycolysis rows ordered M00001.. complete.

### `build_kegg_module_completeness_summary` — verified

Same MATCH + WHERE + class hop; returns `total_entries` (separate `MATCH ()-[:Organism_has_kegg_module]->()` count),
`total_matching`, `by_status` (status, count), `by_organism_status` (organism_name, status,
count), `by_module_status` (module_id, status, count), `by_class_status` (class_id,
class_name, status, count) — each ≤ 4 × axis size. Grouped `WITH … count(*)`
aggregation; api pivots into the envelope shapes. Verified: pathway, all organisms →
total_matching 24,563 = sum of by_status (6,700 + 5,550 + 4,093 + 8,220), 118 organisms,
10 classes.

### `build_kegg_module_completeness_scope` — verified

Status-independent scope: one row per level-3 module in scope with the organisms that have
an edge (no `status` condition):

```cypher
MATCH (m:KeggModule {level: 3})
WHERE ($module_type IS NULL OR m.module_type = $module_type)
  AND ($module_ids IS NULL OR EXISTS { … same expansion … })
MATCH (m)-[:Kegg_module_is_a_kegg_module]->(:KeggModule)-[:Kegg_module_is_a_kegg_module]->(cls:KeggModule)
OPTIONAL MATCH (o:OrganismTaxon)-[:Organism_has_kegg_module]->(m)
WHERE ($organisms IS NULL OR o.preferred_name IN $organisms)
RETURN m.id AS module_id, m.name AS module_name, m.module_type AS module_type,
       cls.id AS class_id, cls.name AS class_name,
       [x IN collect(o.preferred_name) WHERE x IS NOT NULL] AS organisms_with_edge
ORDER BY module_id
```

≤ 414 rows. The api derives `modules_in_scope`, `no_edge_count`,
`by_class[*].module_count` / `.no_edge`, `top_organisms[*].no_edge` (= modules_in_scope −
|modules with an edge for o|), `top_modules[*].no_edge` and, for ≤ 3 modules,
`top_modules[*].organisms_without_edge` (= organisms in scope − organisms_with_edge). The
api sorts and caps `top_organisms` / `top_modules` at 20 (constant `_KMC_TOP_N`).
Verified: nitrogen-metabolism subclass × 3 strains → 7 modules; M00531 without = [MED4];
the other 6 without = all three.

### `build_kegg_module_completeness_resolve`

`UNWIND $module_ids AS mid OPTIONAL MATCH (m:KeggModule {id: mid})` + whether any level-3
module under it matches `module_type` → `not_found_modules` / `not_matched_modules`.

## API (`api/functions.py`)

`kegg_module_completeness(organism=None, module_ids=None, status=None,
module_type='pathway', summary=False, verbose=False, limit=None, offset=0, *, conn=None)`,
wrapped with `@listify_bare_str` like `genes_by_ontology`. Orchestration: resolve organism
scope (`_gbo_resolve_organism_scope`; None → `_gbo_organisms_with_genes` for absence lists,
`$organisms = null` in Cypher) → normalise + resolve module ids → validate `status` /
`module_type` vocab → scope query → summary query → detail query (skipped when `limit=0`).
Short-circuit with an empty well-formed envelope when no organism or no module is in scope.
Export from `api/__init__.py` and `multiomics_explorer/__init__.py`.

## Extensions to existing tools

1. **`list_organisms`** — compact `complete_pathway_module_count: int` = pathway modules with
   status `complete` in this organism (`COUNT { (o)-[:Organism_has_kegg_module {status:'complete'}]->(:KeggModule {module_type:'pathway'}) }`;
   0 for organisms without genes). Equals `kegg_module_completeness(organism=X, status=['complete'], summary=True)` `total_matching` at the default `module_type`. Signature modules are not counted here. Verified: HNLC1 41 (lowest), MED4 51, WH8102 56, Alteromonas HOT1A3 83.
   Description routes to `kegg_module_completeness`.
2. **`ontology_term_details(organism=...)`** — on level-3 `kegg_module` rows only: 
   `organism_module_status: str | None` (the edge's `status`; **null = no step covered** —
   kept as null, not stripped) and `organism_steps_present: int | None`. Absent on every other
   row and when `organism` is not given. Builder: `OPTIONAL MATCH (:OrganismTaxon
   {preferred_name: $organism})-[om:Organism_has_kegg_module]->(t)`.
3. **`list_filter_values`** — new filter types `kegg_module_status`
   (`Organism_has_kegg_module.status`, with value_descriptions) and `module_type`
   (`KeggModule.module_type`), from ControlledVocabulary like the other CV-backed types.
   Lets Build A's invalid-`module_type` hint point somewhere (`_TRUST_FILTER_VALUE_SPECS` /
   equivalent registration).

## Tests

- Unit: builders (columns, verbose split, WHERE pieces present / absent per param, ORDER
  BY, SKIP/LIMIT, module-id expansion clause, status_rank), api (organism modes, id
  normalisation, not_found / not_matched, absence derivation (`no_edge` counts,
  `no_edge_count`), `top_*` cap at 20 + sort, names only at ≤ 3 modules, short-circuits, summary=True skips detail), wrapper (envelope, EXPECTED_TOOLS = 43),
  extensions (list_organisms column, term_details organism columns null-kept, new
  filter types).
- Integration (`-m kg`): M00531 counts (56 / 26 / 0 / 0 complete / one / two / partial; 36
  without edge, MED4 among them); MED4 complete pathway count = list_organisms
  `complete_pathway_module_count`; PCC 7942 × M00161 → no row, in `organisms_without_edge`;
  signature module under default → not_matched + warning; class id expansion; HOT1A3
  glycolysis complete; `ontology_term_details(['kegg.module:M00531'], organism='Prochlorococcus MED4')`
  → `organism_module_status` null, WH8102 → `complete`.
- Edge-case scenarios: unknown module id, empty `module_ids` (raises), organism without
  genes, status filter emptying rows, `limit=0`, offset past end.
- Regression goldens: 3 (single organism summary, M00531 cross-strain, class-expanded
  detail). Evals: 3 cases.
## Docs (doc-updater owns; regenerate with `build_about_content.py --live-vocab`, then `--lint`)

**Generated (never hand-edit; regenerated from yaml + Pydantic):**
- `references/tools/kegg_module_completeness.md` + `tools/full/…` — new, from a new
  `inputs/tools/kegg_module_completeness.yaml` (skeleton via `--skeleton`): examples (MED4
  complete by class; M00531 cross-strain with `organisms_without_edge`; one_step_missing →
  `missing_kos` → `genes_by_function`), chaining, mistakes ("no edge ≠ no genes" with the
  PCC 7942 PSII case; "`complete` ≠ the route runs"; "one KO from `missing_kos` may not
  complete a step"; "`top_*` are capped at 20 — page rows for the whole table";
  "signature ids need `module_type='signature'` or None"), verbose_fields.
- `tools/list_organisms.md`, `tools/ontology_term_details.md`, `tools/list_filter_values.md`
  (+ full pages) — regenerate from the new Pydantic fields; yaml touch-ups: a
  `complete_pathway_module_count` mention / chaining line, an `organism=` module-status
  example on `ontology_term_details`, the two new filter types on `list_filter_values`.
- `tools/genes_by_ontology.md`, `tools/search_ontology.md`, `tools/pathway_enrichment.md`
  (+ full) — chaining line `… → kegg_module_completeness` in their yaml where kegg_module
  examples already sit (gene set ≠ route).
- `references/ontologies/kegg_module.md` (`docs://ontologies/kegg_module`) — from
  `inputs/ontologies/kegg_module.yaml`: `interpretation` and `pitfalls` currently say
  "per-genome completeness lives on the organism-to-module edge … read
  `complete_organism_count`" → route to `kegg_module_completeness`; add a
  `typical_questions` entry ("Does MED4 have a complete assimilatory nitrate reduction
  module?") and `see_also`.
- `references/ontologies/index.md` and `references/index.md` (docs directory, token sizes)
  — regenerate only.

**Hand-authored:**
- `guide/start_here.md` — 42 → 43 tools (line 3); "36 of 42 tools accept `summary=True`" →
  37 of 43; one routing line for module completeness (budget within 10 chars — trim an
  existing line to fit); `list_organisms` capability line mentions module completeness.
- `guide/concepts.md` — KEGG modules row: "per-genome completeness:
  `kegg_module_completeness`".
- `guide/conventions.md` — only if a count / tool list there names 42 (budget within 10
  chars; trim to fit).
- `analysis/enrichment.md` — module section: one line that module ORA tests gene sets, and
  `kegg_module_completeness` says whether the route is complete in the genome.
- `CLAUDE.md` — new tool-table row; "42 functions" → 43; `list_organisms` /
  `ontology_term_details` / `list_filter_values` rows mention the new fields.
- `mcp_server/server.py` instructions "(42 tools)" → 43 (tool-wrapper owns).

**Lint registries:** `inputs/lint/kg_claims.yaml` `tool_count` 42 → 43 (+ quoted strings);
`inputs/lint/stale_identifiers.yaml` add `\b42 tools\b` → "43 tools"; `kg_claims` entries
for any quoted live number (M00531 56 / 26 / 36, MED4 51) if the docs quote them.

## Decisions (review 2026-11-19)

1. Rows sort `module_id` → band → organism.
2. Envelope bounded by caps: `by_status` + `by_class` complete; `top_organisms` /
   `top_modules` capped at 20 (repo convention: `top_*` = capped, `by_*` = complete);
   absence is a `no_edge` count everywhere; organism names without an edge only when
   `modules_in_scope ≤ 3`. No synthetic `no_edge` rows.
3. `module_ids` accepts class ids (expansion) instead of a separate `classes` param.
4. `list_organisms.complete_pathway_module_count` counts pathway modules only.
5. Signature ids under the default `module_type='pathway'` → `not_matched_modules` + warning.
