# list_metabolites — Tool spec (Phase 1)

## Executive Summary

First net-new tool in chemistry slice 1. Cross-organism metabolite discovery
+ filtering, mirroring `list_publications` / `list_derived_metrics` shape:
fulltext search, batch ID inputs with `not_found`, organism / pathway joins,
rich envelope rollups, summary / verbose / limit / offset modes.

The tool defines the **metabolite-discovery surface** that the next two
chemistry tools (`genes_by_metabolite`, `gene_metabolic_role`) anchor on
for drill-down.

**Scope-shaping update (post-design):** The TCDB-CAZy ontology spec landed
in the live KG on 2026-05-02 — see
`multiomics_biocypher_kg/docs/kg-changes/tcdb-cazy-ontologies.md`. The
forward-compat hooks the slice-1 design called out (`evidence_sources`,
`transporter_count`, transport-extended `Organism_has_metabolite` /
`Metabolite_in_pathway` edges) are **all populated today**. This spec
treats them as live, not pre-spec. KG counts in the slice-1 design's
section 1 are stale — current state below.

**2026-05-03 KG updates** (re-verified live; no spec-shape changes, only
field-description tweaks + bumped example values):
- **Substrate-edge rollup.** `Tcdb_family_transports_metabolite` edges
  now exist on every TcdbFamily ancestor (5,762 leaf-only → 13,641
  total), so substrate queries are single-hop at any level. Does NOT
  affect `list_metabolites` Cypher directly — we don't traverse this
  edge. But two downstream effects on properties we surface:
  - `Metabolite.transporter_count` is now **scoped to `tc_specificity`
    leaves** at post-import (filtered to retain "actual transporter
    systems" semantics — would otherwise inflate via ancestors).
  - `Metabolite.gene_count` and `organism_count` re-derive from the
    rolled-up edges, fixing a pre-existing transport-arm undercount.
    Glucose `gene_count` jumps 228 → 320 (etc).
- **Invariant restoration.** `size(m.organism_names) == m.organism_count`
  now holds for ALL 3,025 metabolites (was failing on 952 pre-fix).

## Out of Scope

- `min_transporter_count` filter / `min_gene_count` filter — defer; LLM
  can sort client-side from returned rows. Add when a real workflow demands.
- Top-N tunable for envelope rollups — `top_organisms`, `top_pathways`,
  `by_evidence_source` return top 10 fixed. Add `top_n` param later if needed.
- Pathway-level `KeggTerm.reaction_count` / `metabolite_count` rollups in
  the `top_pathways` envelope — captured as Tier-2 follow-up in slice-1
  design § "Out of scope (slice 1 boundaries)". Pathway rows surface only
  `pathway_id`, `pathway_name`, and `count` here; richer pathway metadata
  goes through `genes_by_ontology(ontology="kegg")` for now.
- TCDB-side discovery (`list_transporter_families`) — outside chemistry
  slice 1 (and would be a sibling of TCDB-CAZy spec follow-ups). TCDB
  families surface today via `gene_ontology_terms(ontology="tcdb")` /
  `genes_by_ontology(ontology="tcdb")` per the TCDB-CAZy explorer hooks.
- Element-count filter (`{"N": 3}` "metabolites with ≥3 N atoms") —
  KG-A3 deferred this; only presence filter today.
- Cross-organism intersection mode (`organism_names=[A,B]` returns
  metabolites where BOTH have it). Slice-1 returns UNION; LLM intersects
  client-side or runs two single-org calls.

## Status / Prerequisites

- [x] Slice-1 design approved
  (`docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md` § 2.1)
- [x] All 4 KG-side asks for slice 1 landed (verified live 2026-05-02 —
  see KG-asks doc § "Build update")
- [x] TCDB-CAZy ontology spec landed (verified live 2026-05-02 — see
  `multiomics_biocypher_kg/docs/kg-changes/tcdb-cazy-ontologies.md`)
- [x] Cypher verified against live KG (see "KG verification" below)
- [x] Result-size controls decided: `summary` / `verbose` / `limit` /
  `offset` mirroring `list_publications` exactly
- [x] **Follow-up KG-asks landed** (2026-05-02 rebuild):
  `docs/superpowers/specs/2026-05-02-kg-side-chemistry-slice1-followup-asks.md` —
  all 4 `Metabolite` denormalizations (`pathway_ids`, `pathway_names`,
  `pathway_count`, `organism_names`) populated 100% (3,025/3,025);
  `size(m.organism_names) == m.organism_count` invariant holds. Spec
  uses the rollup-based Cypher directly; no fallback branch needed.
- [ ] Ready for Phase 2 (build) — pending user approval of this spec

## Use cases

- **Discovery entry point.** N-source workflow step 3:
  `list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"])`
  catalogues nitrogen-bearing metabolites MED4 is capable of metabolizing
  OR transporting (post-TCDB). Sanity check after step 2's gene-anchored
  drill-down.
- **Cross-feeding capability.** Workflow B step 1:
  `list_metabolites(organism_names=["Prochlorococcus MED4", "Alteromonas macleodii ..."])`
  surfaces metabolites both organisms reach (UNION; LLM filters per-row
  by `organism_count` and inspects `m.organism_names` for the full
  UNION reach list). Per-organism gene tallies live in the dedicated
  drill-down `genes_by_metabolite(metabolite_ids=[id], organism=...)`.
- **Pathway-anchored drill-down.** Browse metabolites in a specific KEGG
  pathway:
  `list_metabolites(pathway_ids=["kegg.pathway:ko00910"])` →
  18 metabolites in nitrogen metabolism.
- **Routing to drill-downs.** When `gene_count > 0`, drill into
  `genes_by_metabolite(metabolite_ids=[id], organism=...)` to find the
  catalysts (or transporters once that surface ships).
- **Routing to ontology surface.** `pathway_ids` on each row routes to
  `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)`
  for genes annotated in the pathway.

## KG dependencies

### Nodes & properties read

`Metabolite`:
- `id` (str, full prefixed ID — `kegg.compound:C*` for 2,573 / `chebi:*` for 452)
- `name` (str)
- `formula` (str | null — null on 279 metabolites, mostly transport-only generic ChEBI)
- `elements` (list[str]) — KG-A3 — null when formula is null (effectively empty)
- `mass` (float | null — null on 668 metabolites)
- `chebi_id` (str | null — populated on 90% / 2,724)
- `hmdb_id` (str | null — populated on 47% / 1,425)
- `mnxm_id` (str | null — populated on 100% / 3,025)
- `inchikey`, `smiles` (str | null — verbose fields)
- `gene_count` (int) — 2-hop UNION rollup post-TCDB
- `organism_count` (int) — UNION rollup post-TCDB
- `evidence_sources` (list[str]) — TCDB-CAZy: `metabolism` / `transport` (open-ended for `metabolomics`)
- `transporter_count` (int) — TCDB-CAZy

`OrganismTaxon`:
- `preferred_name` — for `organism_names` filter (case-insensitive match)

`KeggTerm` (pathway-level):
- `id` — for `pathway_ids` filter (e.g. `kegg.pathway:ko00910`)
- `name` — for `top_pathways` envelope display
- `level_kind = 'pathway'` discriminator

### Edges traversed

**None.** All filters and per-row fields read denormalized properties
on `Metabolite` directly (KG-A5..A8). Per-organism gene tallies, when
needed, live in the dedicated drill-down `genes_by_metabolite` (Tool
#2 of slice 1) — explicitly out of scope for this discovery surface.

Both `Reaction_has_metabolite` and `Tcdb_family_transports_metabolite`
edges *exist* and would be reachable for verbose per-row signals, but
the chemistry-slice-1 design prefers to delegate per-gene detail to
the drill-down tool rather than partially duplicate it here.

### Denormalized list / scalar properties consumed (KG-A5..A8, landed 2026-05-02)

The detail builder reads these directly — no edge traversal for filters
or per-row pathway / organism collection:

| Property | Source rollup | Slice-1 use |
|---|---|---|
| `Metabolite.pathway_ids: list[str]` | `Metabolite_in_pathway` distinct rollup | `pathway_ids` filter (ANY-in-list); per-row `pathway_ids` field |
| `Metabolite.pathway_names: list[str]` | aligned with `pathway_ids` (sorted by pathway_id) | verbose per-row `pathway_names` field |
| `Metabolite.pathway_count: int` | distinct count | per-row `pathway_count` routing signal |
| `Metabolite.organism_names: list[str]` | `Organism_has_metabolite` distinct rollup (UNION'd post-TCDB) | `organism_names` filter (ANY-in-list with toLower) |

### Indexes

- `metaboliteFullText`: NODE-level fulltext on **`name` only** (verified
  live — slice-1 design said "covers name + formula" but the index
  reflects the build state and does NOT include `formula`. Element /
  formula-substring filtering goes through the `elements` filter, which
  is the right primitive anyway).

---

## Live-KG state snapshot (verified 2026-05-02)

| Quantity | Value | Notes |
|---|---|---|
| Total Metabolite nodes | 3,025 | Was 2,188 pre-TCDB |
| `with_formula` | 2,746 | 91% — 279 lack formula (mostly TCDB-only ChEBI generics) |
| `with_elements` | 2,745 | tracks `with_formula` |
| `with_evidence_sources` | 3,025 | 100% (post-TCDB) |
| `with_transporter_count` | 3,025 | 100% (post-TCDB) |
| `with_chebi_id` | 2,724 | 90% (kegg.compound:* cross-refs) + 100% on chebi:* IDs (numeric portion stored as `chebi_id` too) |
| `with_hmdb_id` | 1,425 | 47% |
| `with_mnxm_id` | 3,025 | 100% |
| `with_pathway_ids` (KG-A5) | 3,025 | 100% (empty list when no edges) |
| `with_pathway_names` (KG-A6) | 3,025 | 100% (aligned with `pathway_ids`) |
| `with_pathway_count` (KG-A7) | 3,025 | 100% (max 35 — D-Glucose) |
| `with_organism_names` (KG-A8) | 3,025 | 100% (`size(organism_names) == organism_count` invariant holds) |
| `with_inchikey` | 2,355 | 78% |
| `with_smiles` | 2,529 | 84% |
| `with_mass` | 2,357 | 78% |
| `evidence_sources = ['metabolism']` | 1,928 | metabolism-only (Reaction-reachable; no TCDB transport annotation) |
| `evidence_sources = ['transport']` | 837 | transport-only (TCDB) |
| `evidence_sources = ['metabolism','transport']` | 260 | both |
| ID prefix `kegg.compound:` | 2,573 | |
| ID prefix `chebi:` | 452 | TCDB-only non-KEGG substrates (e.g. 'tetracycline') |
| `'N' IN elements` | 1,563 | 1,212 metabolism + 491 transport |
| `'N' AND 'P' IN elements` | 556 | AND-of-presence semantics |
| `Metabolite_in_pathway` distinct pathways | 395 | edge count 9,444 |
| `Organism_has_metabolite` edges | ~56,898 | UNION'd post-TCDB |
| `Tcdb_family_transports_metabolite` edges | 13,641 | rolled-up 2026-05-03 (tc_class 1,497 / tc_subclass 1,510 / tc_family 2,040 / tc_subfamily 2,832 / tc_specificity 5,762). `Metabolite.transporter_count` is leaf-only so the surface value is unaffected by ancestor edges. |
| MED4 `organism_names` distinct metabolites | 1,550 | (catalysis + transport, post-rollup) |
| MED4 N-metabolites | 804 | catalysis-or-transport reachable |
| Metabolites with `gene_count = 0` (post-2026-05-03 fix) | 0 / 3,025 | every Metabolite reaches at least one gene via catalysis or transport. Pre-fix, ~692/837 transport-only had gene_count=0 (genes annotated above leaf level were missed). Future metabolomics-DM metabolites will reintroduce the gene_count=0 case. |

---

## Tool Signature

```python
@mcp.tool(
    tags={"metabolites", "chemistry", "discovery"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def list_metabolites(
    ctx: Context,
    search: Annotated[str | None, Field(
        description="Free-text search on metabolite name (Lucene syntax). "
        "Index covers Metabolite.name only — element/formula composition "
        "is filtered through `elements` (presence list), not search. "
        "E.g. 'glucose', 'phosphate AND amino'.",
    )] = None,
    metabolite_ids: Annotated[list[str] | None, Field(
        description="Restrict to specific metabolites by full prefixed ID "
        "(case-sensitive). E.g. ['kegg.compound:C00031', 'kegg.compound:C00002']. "
        "Combines with other filters via AND. `not_found.metabolite_ids` "
        "lists any IDs that don't exist in the KG.",
    )] = None,
    kegg_compound_ids: Annotated[list[str] | None, Field(
        description="Filter by raw KEGG C-numbers (e.g. ['C00031']). "
        "Convenience over `metabolite_ids` when working with KEGG-anchored "
        "data; the prefixed equivalent is `kegg.compound:C*`.",
    )] = None,
    chebi_ids: Annotated[list[str] | None, Field(
        description="Filter by raw ChEBI numeric IDs (e.g. ['4167', '15422']). "
        "90% of Metabolite nodes carry a `chebi_id`.",
    )] = None,
    hmdb_ids: Annotated[list[str] | None, Field(
        description="Filter by raw HMDB IDs (e.g. ['HMDB0000122']). "
        "47% coverage.",
    )] = None,
    mnxm_ids: Annotated[list[str] | None, Field(
        description="Filter by raw MetaNetX IDs (e.g. ['MNXM1364061']). "
        "100% coverage — every Metabolite has a `mnxm_id`.",
    )] = None,
    elements: Annotated[list[str] | None, Field(
        description="Element-presence filter (Hill-notation symbols). "
        "AND of presence — ['N', 'P'] matches metabolites containing BOTH. "
        "Replaces error-prone formula-substring matching. Empty/null "
        "formula metabolites (~10%) never match. E.g. ['N'] for "
        "nitrogen-containing metabolites (yields 1,563 today).",
    )] = None,
    mass_min: Annotated[float | None, Field(
        description="Minimum monoisotopic mass (Da). Excludes metabolites "
        "with null `mass` (~22%). E.g. 60.0.",
    )] = None,
    mass_max: Annotated[float | None, Field(
        description="Maximum monoisotopic mass (Da). E.g. 1000.0.",
    )] = None,
    organism_names: Annotated[list[str] | None, Field(
        description="Restrict to metabolites reachable by these organisms "
        "(case-insensitive on `preferred_name`). UNION semantics — a "
        "metabolite reached by ANY listed organism qualifies. Joined via "
        "`Organism_has_metabolite` (catalysis OR transport post-TCDB). "
        "E.g. ['Prochlorococcus MED4']. `not_found.organism_names` lists "
        "any unknown names.",
    )] = None,
    pathway_ids: Annotated[list[str] | None, Field(
        description="Filter by KEGG pathway membership (`KeggTerm.id`). "
        "E.g. ['kegg.pathway:ko00910'] for nitrogen metabolism. Joined via "
        "`Metabolite_in_pathway` (transport-extended post-TCDB; 395 distinct "
        "pathways are metabolite-reachable). `not_found.pathway_ids` lists "
        "any IDs that don't exist as a KeggTerm.",
    )] = None,
    evidence_sources: Annotated[
        list[Literal["metabolism", "transport", "metabolomics"]] | None,
        Field(
            description="Filter by evidence path. Set-membership ANY semantics "
            "— ['transport'] returns transport-only AND dual (1,097 today). "
            "Valid values: 'metabolism' (catalysis-reachable), 'transport' "
            "(TCDB-curated substrate). `'metabolomics'` is accepted as a "
            "filter value for forward-compat with the future metabolomics-DM "
            "spec; no row matches yet. Other values raise at the MCP "
            "boundary (Pydantic Literal validation).",
        ),
    ] = None,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include heavy-text and structural-fingerprint fields "
        "(inchikey, smiles, mnxm_id, hmdb_id, pathway_names).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
    offset: Annotated[int, Field(
        description="Number of results to skip for pagination.", ge=0,
    )] = 0,
) -> ListMetabolitesResponse:
    """Browse and filter metabolites in the chemistry layer.

    **Direction-agnostic.** Joins through `Reaction_has_metabolite` and
    (post-TCDB) `Tcdb_family_transports_metabolite` are direction-agnostic —
    a metabolite that is *produced* and one that is *consumed* surface
    identically. KEGG equation order is arbitrary. To distinguish, layer
    transcriptional evidence (`differential_expression_by_gene`) and
    functional annotation (`gene_overview` Pfam/KO `*-synthase` vs
    `*-permease`).

    After this tool, drill in via:
    - genes_by_metabolite(metabolite_ids=[id], organism=...) — find the
      catalysts / transporters per organism (replaces what would
      otherwise be an inline per-row top-N gene list here)
    - gene_metabolic_role(locus_tags=[...], organism=..., metabolite_elements=...) — gene-centric chemistry
    - genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...) — pathway → genes
    """
```

**Return envelope:**

```python
class ListMetabolitesResponse(BaseModel):
    total_entries: int        # All Metabolite nodes (3,025 today)
    total_matching: int       # After filters
    top_organisms: list[MetTopOrganism]                  # top 10 (truncated)
    top_pathways: list[MetTopPathway]                    # top 10 (truncated)
    by_evidence_source: list[MetEvidenceSourceBreakdown] # full frequency rollup (1-3 entries)
    xref_coverage: MetXrefCoverage                       # {with_chebi, with_hmdb, with_mnxm}
    mass_stats: MetMassStats                             # {min, median, max} | nulls when no mass
    returned: int
    offset: int
    truncated: bool
    not_found: MetNotFound                               # {metabolite_ids, organism_names, pathway_ids}
    results: list[MetaboliteResult]
```

**Naming convention:** `top_*` for hardcoded top-N rollups (truncated; the
list does NOT exhaust the matched set); `by_*` for full frequency
rollups (every distinct value present in the matched set, sorted desc by
count). The convention is project-new — see "Open questions" for the
retroactive question about `list_organisms.by_metabolic_capability`.

**Per-result `MetaboliteResult` (compact):**

| Field | Type | Notes |
|---|---|---|
| `metabolite_id` | str | `kegg.compound:C00031` (full prefixed) |
| `name` | str | `D-Glucose` |
| `formula` | str \| None | `C6H12O6` (sparse — null on ~9%) |
| `elements` | list[str] | `['C','H','O']` (empty for null formula) |
| `mass` | float \| None | `180.156` (sparse — null on ~22%) |
| `gene_count` | int | UNION across catalysis + transport (e.g. 320 for glucose). All current metabolites have gene_count > 0 post-2026-05-03 fix; future metabolomics-only metabolites will reintroduce the 0 case. |
| `organism_count` | int | UNION (e.g. 31 for glucose) |
| `transporter_count` | int | TCDB families curating this as substrate (e.g. 17) |
| `evidence_sources` | list[str] | `['metabolism','transport']` |
| `chebi_id` | str \| None | Sparse-stripped when null |
| `pathway_ids` | list[str] | KEGG pathway memberships; empty when no edges |
| `pathway_count` | int | Distinct pathway count (e.g. 5). Routing signal — when > 0 drill into `genes_by_ontology(ontology="kegg", term_ids=[id], organism=...)`. (Surfaces post-KG-A7; pre-A7 computed from list size.) |

**Verbose adds:**

| Field | Type | Notes |
|---|---|---|
| `inchikey` | str \| None | structural fingerprint |
| `smiles` | str \| None | structural fingerprint |
| `mnxm_id` | str \| None | always populated today |
| `hmdb_id` | str \| None | sparse |
| `pathway_names` | list[str] | Aligned with `pathway_ids` |

## Result-size controls

`summary` / `verbose` / `limit` / `offset` mirror `list_publications`
exactly. Default `limit = 5` (small, summary + a few example rows in one
call).

**Sort key:** `m.organism_count DESC, m.gene_count DESC, m.id` — surfaces
metabolites with broadest organism coverage first (useful for cross-feeding
discovery), with `m.id` as deterministic tiebreaker. Empty-coverage
metabolites end up at the bottom but still pageable.

## Special handling

- **Lucene retry for `search`:** mirrors `list_publications` — on
  `Neo4jClientError`, retry with `_LUCENE_SPECIAL` escape.
- **`organism_names` filter:** flat ANY-in-list against
  `m.organism_names` (KG-A8). UNION semantics — a metabolite reached
  by ANY listed organism qualifies. Case-insensitive via `toLower()`
  on both sides.
- **`pathway_ids` filter:** flat ANY-in-list against `m.pathway_ids`
  (KG-A5).
- **`evidence_sources` filter:** ANY semantics on the array property —
  `ANY(s IN $evidence_sources WHERE s IN m.evidence_sources)`.
- **`elements` filter is AND-of-presence:** `ALL(e IN $elements WHERE e IN m.elements)`.
- **Per-row `pathway_ids` / `pathway_count`:** plain property reads via
  `coalesce(m.pathway_ids, []) AS pathway_ids` / `coalesce(m.pathway_count, 0) AS pathway_count`.
  Verbose `pathway_names` similarly (KG-A6, sorted aligned with `pathway_ids`).
- **Per-organism gene tallies are out of scope here** — the dedicated
  drill-down `genes_by_metabolite(metabolite_ids=[id], organism=...)`
  (slice-1 Tool #2) does the metabolite → genes per organism breakdown
  with full filter support (ec_numbers, pathway_ids, gene_categories,
  evidence_sources). Avoiding partial duplication in this discovery
  tool keeps the verbose detail Cypher 100% property reads — zero
  per-row edge traversal at any scale.
- **`not_found` is a typed dict** keyed by filter type
  (`metabolite_ids`, `organism_names`, `pathway_ids`). Mirrors
  `list_experiments` envelope shape.
- **Sparse-strip in api/:** drop `chebi_id` when null (Pydantic field is
  optional). Mass stays as `Optional[float]`.
- **`coalesce(m.<prop>, default)` defensive even on populated props** —
  null safety against any pre-rebuild row that might slip through; one
  line per RETURN column, no cost.

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `_list_metabolites_where()` shared helper, `build_list_metabolites()`, `build_list_metabolites_summary()`. |
| 2 | API function | `api/functions.py` | `list_metabolites()`. Lucene retry. Builds typed `not_found` dict from id-batch lookups. Computes envelope rollups from summary builder result. |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add `list_metabolites` to imports + `__all__`. |
| 4 | MCP wrapper | `mcp_server/tools.py` | `MetaboliteResult`, `ListMetabolitesResponse`, `MetTopOrganism`, `MetTopPathway`, `MetEvidenceSourceBreakdown`, `MetXrefCoverage`, `MetMassStats`, `MetNotFound`, `@mcp.tool` wrapper. Update `EXPECTED_TOOLS`. |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildListMetabolites` + `TestBuildListMetabolitesSummary`. |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `TestListMetabolites` — mocked-conn fixtures. |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestListMetabolitesWrapper`. Update `EXPECTED_TOOLS`. |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Live-KG smoke test (`elements=["N"]`, MED4 + N elements, pathway_ids ko00910, search "glucose"). |
| 8b | Integration | `tests/integration/test_api_contract.py` | `TestListMetabolitesContract`. |
| 9 | Regression | `tests/regression/test_regression.py` + `tests/evals/test_eval.py` | Add `list_metabolites: build_list_metabolites` to both `TOOL_BUILDERS` dicts. |
| 10 | Eval cases | `tests/evals/cases.yaml` | 4-6 cases (empty / `elements=[N]` / pathway_ids / organism_names + elements / search / id-batch with not_found). |
| 11 | About content | `multiomics_explorer/inputs/tools/list_metabolites.yaml` | examples + chaining + mistakes; run `build_about_content.py`. |
| 12 | Docs | `CLAUDE.md` | Add `list_metabolites` row to MCP tool table. |

---

## Query Builder

**File:** `kg/queries_lib.py`

### Shared `_list_metabolites_where()`

Mirrors `_list_publications_where()` shape — returns `(where_block, params)`.
Each filter contributes one `conditions.append(...)` call.

```python
def _list_metabolites_where(
    *,
    search: str | None = None,                        # not in WHERE — selects entry point
    metabolite_ids: list[str] | None = None,
    kegg_compound_ids: list[str] | None = None,
    chebi_ids: list[str] | None = None,
    hmdb_ids: list[str] | None = None,
    mnxm_ids: list[str] | None = None,
    elements: list[str] | None = None,
    mass_min: float | None = None,
    mass_max: float | None = None,
    organism_names_lc: list[str] | None = None,
    pathway_ids: list[str] | None = None,
    evidence_sources: list[str] | None = None,
) -> tuple[str, dict]:
    """Build WHERE clause and params for metabolite queries.

    Shared between build_list_metabolites and build_list_metabolites_summary.
    `search` is not added to WHERE — it controls which Cypher variant is
    used (fulltext entry point vs MATCH). The $search param is added to
    params when search is provided.
    """
```

WHERE fragments:

| Filter | Fragment |
|---|---|
| `metabolite_ids` | `m.id IN $metabolite_ids` |
| `kegg_compound_ids` | `m.kegg_compound_id IN $kegg_compound_ids` |
| `chebi_ids` | `m.chebi_id IN $chebi_ids` |
| `hmdb_ids` | `m.hmdb_id IN $hmdb_ids` |
| `mnxm_ids` | `m.mnxm_id IN $mnxm_ids` |
| `elements` | `ALL(e IN $elements WHERE e IN coalesce(m.elements, []))` |
| `mass_min` | `m.mass >= $mass_min` |
| `mass_max` | `m.mass <= $mass_max` |
| `organism_names_lc` | `ANY(o IN coalesce(m.organism_names, []) WHERE toLower(o) IN $organism_names_lc)` |
| `pathway_ids` | `ANY(p IN coalesce(m.pathway_ids, []) WHERE p IN $pathway_ids)` |
| `evidence_sources` | `ANY(s IN $evidence_sources WHERE s IN coalesce(m.evidence_sources, []))` |

### `build_list_metabolites` (detail)

```python
def build_list_metabolites(
    *,
    search: str | None = None,
    metabolite_ids: list[str] | None = None,
    kegg_compound_ids: list[str] | None = None,
    chebi_ids: list[str] | None = None,
    hmdb_ids: list[str] | None = None,
    mnxm_ids: list[str] | None = None,
    elements: list[str] | None = None,
    mass_min: float | None = None,
    mass_max: float | None = None,
    organism_names_lc: list[str] | None = None,
    pathway_ids: list[str] | None = None,
    evidence_sources: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for listing metabolites.

    RETURN keys (compact): metabolite_id, name, formula, elements, mass,
    gene_count, organism_count, transporter_count, evidence_sources,
    chebi_id, pathway_ids, pathway_count.
    When search is provided, also: score.
    RETURN keys (verbose): adds inchikey, smiles, mnxm_id, hmdb_id,
    pathway_names. All verbose columns are direct property reads on m;
    no edge traversal in either compact or verbose mode.
    """
```

Cypher shape (no-search variant):

```cypher
MATCH (m:Metabolite)
WHERE <conditions>
RETURN m.id AS metabolite_id,
       m.name AS name,
       m.formula AS formula,
       coalesce(m.elements, []) AS elements,
       m.mass AS mass,
       coalesce(m.gene_count, 0) AS gene_count,
       coalesce(m.organism_count, 0) AS organism_count,
       coalesce(m.transporter_count, 0) AS transporter_count,
       coalesce(m.evidence_sources, []) AS evidence_sources,
       m.chebi_id AS chebi_id,
       coalesce(m.pathway_ids, []) AS pathway_ids,
       coalesce(m.pathway_count, 0) AS pathway_count
       <verbose_cols>
ORDER BY m.organism_count DESC, m.gene_count DESC, m.id
SKIP $offset LIMIT $limit
```

Verbose columns (added when `verbose=True` — all direct property reads
on `m`, no edge traversal, no CALL subquery):

```cypher
,
m.inchikey AS inchikey,
m.smiles AS smiles,
m.mnxm_id AS mnxm_id,
m.hmdb_id AS hmdb_id,
coalesce(m.pathway_names, []) AS pathway_names
```

Search-variant entry point — same RETURN shape, just a different
match clause + score column:

```cypher
CALL db.index.fulltext.queryNodes('metaboliteFullText', $search) YIELD node AS m, score
WHERE <conditions>
RETURN <same compact + verbose RETURN columns as no-search variant>, score
ORDER BY score DESC, m.organism_count DESC, m.id
SKIP $offset LIMIT $limit
```

Verified live (`search='glucose'` → 3 results, top is generic 'glucose'
chebi:14313 score 3.04, then UDP-glucose and D-Glucose tied at 2.56).

### `build_list_metabolites_summary` (envelope)

```python
def build_list_metabolites_summary(
    *,  # same filter params as detail
) -> tuple[str, dict]:
    """Build summary aggregation Cypher for list_metabolites.

    RETURN keys: total_entries, total_matching, top_organisms, top_pathways,
    by_evidence_source, with_chebi, with_hmdb, with_mnxm, mass_min,
    mass_median, mass_max.
    When search is provided, also: score_max, score_median.
    """
```

Cypher shape (no-search variant):

```cypher
MATCH (m:Metabolite)
WITH count(m) AS total_entries
OPTIONAL MATCH (m:Metabolite)
WHERE <conditions>
// Aggregate scalars + flatten denormalized list properties in one WITH.
// Critically: no `collect(m) AS matched` — we never hold matched-Metabolite
// node objects in memory. Instead we collect cheap flat lists from the
// rollup properties (KG-A5..A8) and process them with apoc.
WITH total_entries,
     count(m) AS total_matching,
     apoc.coll.flatten(collect(coalesce(m.evidence_sources, []))) AS es,
     apoc.coll.flatten(collect(coalesce(m.organism_names, []))) AS all_orgs,
     apoc.coll.flatten(collect(coalesce(m.pathway_ids, []))) AS all_pwys,
     count(m.chebi_id) AS with_chebi,
     count(m.hmdb_id) AS with_hmdb,
     count(m.mnxm_id) AS with_mnxm,
     collect(m.mass) AS masses
// top_organisms: frequency-count flattened org list, top 10 in Cypher
CALL {
  WITH all_orgs
  UNWIND apoc.coll.frequencies(all_orgs) AS f
  WITH f.item AS organism_name, f.count AS count
  ORDER BY count DESC LIMIT 10
  RETURN collect({organism_name: organism_name, count: count}) AS top_organisms
}
// top_pathways: same, then index-lookup KeggTerm.name for each top-10 ID
CALL {
  WITH all_pwys
  UNWIND apoc.coll.frequencies(all_pwys) AS f
  WITH f.item AS pathway_id, f.count AS count
  ORDER BY count DESC LIMIT 10
  OPTIONAL MATCH (p:KeggTerm {id: pathway_id})
  RETURN collect({
    pathway_id: pathway_id, pathway_name: p.name, count: count
  }) AS top_pathways
}
RETURN total_entries, total_matching,
       apoc.coll.frequencies(es) AS by_evidence_source,
       with_chebi, with_hmdb, with_mnxm,
       apoc.coll.min(masses) AS mass_min,
       apoc.coll.sort(masses)[size(masses)/2] AS mass_median,
       apoc.coll.max(masses) AS mass_max,
       top_organisms, top_pathways
```

The `OPTIONAL MATCH` after `total_entries` follows the
`build_list_publications_summary` pattern — preserves the row when the
filter intersection is empty, so callers can `[0]`-index summary safely.

**Memory profile:** with no filters (3,025 metabolites matched), the
flattened lists size to roughly: `es` ~3.3K strings (1.1 avg per
metabolite), `all_orgs` ~57K strings (~19 orgs avg), `all_pwys` ~9.4K
strings, `masses` 2,357 floats. Total ~70K small primitives — well
within Neo4j heap. The pre-refactor `collect(m) AS matched` would have
held 3,025 Metabolite **node objects** with all their properties.

Search variant — fulltext entry point + `score` collection; otherwise
identical envelope shape:

```cypher
CALL db.index.fulltext.queryNodes('metaboliteFullText', $search) YIELD node AS m, score
WITH count(m) AS total_matching,
     apoc.coll.flatten(collect(coalesce(m.evidence_sources, []))) AS es,
     apoc.coll.flatten(collect(coalesce(m.organism_names, []))) AS all_orgs,
     apoc.coll.flatten(collect(coalesce(m.pathway_ids, []))) AS all_pwys,
     count(m.chebi_id) AS with_chebi,
     count(m.hmdb_id) AS with_hmdb,
     count(m.mnxm_id) AS with_mnxm,
     collect(m.mass) AS masses,
     collect(score) AS scores
// total_entries comes from a small unfiltered Metabolite count
MATCH (m2:Metabolite)
WITH count(m2) AS total_entries, total_matching, es, all_orgs, all_pwys,
     with_chebi, with_hmdb, with_mnxm, masses, scores
CALL { /* top_organisms — same as no-search */ }
CALL { /* top_pathways — same as no-search */ }
RETURN total_entries, total_matching,
       apoc.coll.frequencies(es) AS by_evidence_source,
       with_chebi, with_hmdb, with_mnxm,
       apoc.coll.min(masses) AS mass_min,
       apoc.coll.sort(masses)[size(masses)/2] AS mass_median,
       apoc.coll.max(masses) AS mass_max,
       apoc.coll.max(scores) AS score_max,
       apoc.coll.sort(scores)[size(scores)/2] AS score_median,
       top_organisms, top_pathways
```

Verified live: `search='glucose'` → 23 matching, score_max=3.04,
score_median=1.74, top_pathways led by Metabolic pathways (18 metabolites).

### KG verification

| Query | Expected | Actual | Pass |
|---|---|---|---|
| Total metabolites | 3,025 | 3,025 | ✓ |
| `elements=['N']` | 1,563 | 1,563 | ✓ |
| `elements=['N','P']` | 556 | 556 | ✓ |
| `evidence_sources` distribution | 1928/837/260 | 1928/837/260 | ✓ |
| `pathway_ids=['kegg.pathway:ko00910']` | 18 | 18 | ✓ |
| MED4 reachable | 1,550 (UNION) | 1,550 | ✓ |
| MED4 + `elements=['N']` | 804 | 804 | ✓ |
| Glucose lookup `kegg.compound:C00031` | gene_count=320, organism_count=31, transporter_count=17, evidence=both | matches | ✓ (gene_count was 228 pre-2026-05-03 fix) |
| Detail sort top — `elements=['N']`, MED4 | ATP, ADP, NAD+, NADH, AMP | matches | ✓ |
| `metaboliteFullText` index | NODE / Metabolite / [name] | confirmed | ✓ |
| ID prefix distribution | 2,573 kegg.compound + 452 chebi | confirmed | ✓ |
| Distinct pathway count via Metabolite_in_pathway | 395 | 395 | ✓ |
| KG-A5..A8 properties populated | 100% (3,025/3,025 each) | 100% | ✓ |
| Glucose `pathway_ids` length | 35 | 35 | ✓ |
| Glucose `pathway_names` aligned with `pathway_ids` | yes | yes (`Glycolysis / Gluconeogenesis` first) | ✓ |
| Glucose `pathway_count` matches `size(pathway_ids)` | 35 == 35 | 35 == 35 | ✓ |
| Glucose `organism_names` length matches `organism_count` | 31 == 31 | 31 == 31 | ✓ |
| `pathway_ids` contains `kegg.pathway:ko00910` → 18 metabolites | 18 (= legacy edge-join count) | 18 | ✓ |
| `chebi_id` populated on chebi:-prefixed metabolites | 100% | 452/452 | ✓ |

**Variable scoping check:** Summary builder uses `WITH total_entries` + `OPTIONAL MATCH` to preserve total_entries through the chain. The two CALL subqueries explicitly consume their inputs (`WITH all_orgs` / `WITH all_pwys`) — no implicit scoping. Verified by running the summary query against `elements=['N']` with and without organism filter, plus the empty-result case (filter → 0 matches; summary still returns 1 row with `total_matching=0`, all rollups empty/null).

**Design notes:**
- `m.id` final tiebreaker (deterministic across rebuilds).
- `pathway_ids` and `pathway_names` are property reads off `m`
  (KG-A5/A6) — single MATCH, no per-row traversals or UNWIND.
- Search-variant ORDER BY drops `gene_count` from the tiebreaker chain
  (`ORDER BY score DESC, m.organism_count DESC, m.id` only) since
  Lucene score is the dominant signal; gene_count tiebreaker only matters
  among score-equivalent rows, where organism_count is a more meaningful
  next-axis. Detail variant uses the full chain.
- All current metabolites have `gene_count > 0` (post-2026-05-03 fix), so the default sort surfaces real reach across the full set. The "low-coverage tail" pattern (transport-only with gene_count=0) was the pre-fix narrative; not applicable today.

---

## API Function

**File:** `api/functions.py`

```python
def list_metabolites(
    search: str | None = None,
    metabolite_ids: list[str] | None = None,
    kegg_compound_ids: list[str] | None = None,
    chebi_ids: list[str] | None = None,
    hmdb_ids: list[str] | None = None,
    mnxm_ids: list[str] | None = None,
    elements: list[str] | None = None,
    mass_min: float | None = None,
    mass_max: float | None = None,
    organism_names: list[str] | None = None,
    pathway_ids: list[str] | None = None,
    evidence_sources: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List metabolites in the chemistry layer with rich filtering.

    Returns dict with keys: total_entries, total_matching, returned, offset,
    truncated, top_organisms, top_pathways, by_evidence_source, xref_coverage,
    mass_stats, not_found, results.
    Per result (compact): metabolite_id, name, formula, elements, mass,
    gene_count, organism_count, transporter_count, evidence_sources,
    chebi_id (sparse), pathway_ids, pathway_count.
    When verbose=True, also includes: inchikey, smiles, mnxm_id, hmdb_id,
    pathway_names. (For per-organism gene tallies, drill into
    genes_by_metabolite — slice-1 Tool #2.)
    When search is provided, also includes score (per row) + score_max,
    score_median (envelope).

    Raises:
        ValueError: if search is empty/whitespace. (evidence_sources is
                   typed as Literal in the wrapper signature — invalid
                   values raise at the MCP boundary, not here.)
    """
```

API responsibilities:
1. Validate `search` non-empty (when provided). `evidence_sources` is
   typed at the MCP boundary (`Literal[...]`); api/ may receive Python
   `list[str]` from non-MCP callers and should still validate against
   the same enum for consistency.
2. Lowercase `organism_names` for the WHERE clause.
3. `summary=True` → set `limit = 0` internally.
4. Run summary builder first (always). The Cypher returns:
   - `total_entries`, `total_matching` — flat ints
   - `top_organisms`, `top_pathways` — already-nested + already-sorted
     top-10 list of dicts (Cypher does the apoc.coll.frequencies +
     UNWIND + ORDER BY + LIMIT 10 + collect chain; api/ never sees
     the underlying frequency map).
   - `by_evidence_source` — apoc.coll.frequencies output
     (`[{item, count}]`); api/ renames `item` → `evidence_source` via
     `_rename_freq`.
   - `with_chebi`, `with_hmdb`, `with_mnxm` — flat ints; api/ wraps
     into `MetXrefCoverage` dict.
   - `mass_min`, `mass_median`, `mass_max` — flat floats (any of the
     three may be null when matched set has no metabolite with a mass);
     api/ wraps into `MetMassStats` dict.
   - `score_max`, `score_median` (search variant only) — flat floats.
5. Run detail builder when `limit != 0`. Lucene retry on `Neo4jClientError`.
   Detail RETURN columns are pure property reads on `m` regardless of
   `verbose` — no edge traversal, no per-row CALL subqueries.
6. Sparse-strip null `chebi_id` from rows.
7. Compute typed `not_found` dict by running quick existence checks on
   `metabolite_ids` / `organism_names` / `pathway_ids` (parallel to
   `list_publications`'s DOI not_found check; one small Cypher per
   provided filter — `RETURN collect(...) AS found`; empty input skips
   the query).
8. Assemble + return the dict.

Reuses `_LUCENE_SPECIAL` regex for retry — same pattern as `list_publications`.

**Layer-rules note:** zero per-row Python aggregation. All breakdowns
(top-N rollups, frequency rollups, mass / score stats) are computed in
Cypher with apoc — api/ only renames keys and wraps flat values into
nested Pydantic-shaped dicts. Lets the tool stream rows naturally
under `limit`/`offset` without needing to hold full result sets in
memory for post-processing.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

### Pydantic models

```python
class MetaboliteResult(BaseModel):
    # compact
    metabolite_id: str = Field(description="Full prefixed ID (e.g. 'kegg.compound:C00031'). 85% kegg.compound, 15% chebi (TCDB-only substrates).")
    name: str = Field(description="Metabolite name (e.g. 'D-Glucose', 'L-Glutamate')")
    formula: str | None = Field(default=None, description="Hill-notation chemical formula (e.g. 'C6H12O6'). Null on ~9% of metabolites (mostly TCDB-curated generic substrates).")
    elements: list[str] = Field(default_factory=list, description="Sorted unique element symbols present in formula (e.g. ['C','H','O']). Empty when formula is null. Filter on this — never on `formula` substring (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N').")
    mass: float | None = Field(default=None, description="Monoisotopic mass in Da (e.g. 180.156). Null on ~22% of metabolites.")
    gene_count: int = Field(default=0, description="Distinct genes reachable via Gene → Reaction → Metabolite OR Gene → TcdbFamily → Metabolite (UNION post-TCDB; e.g. 320 for glucose). When > 0, drill in via genes_by_metabolite(metabolite_ids=[id], organism=...). All metabolites have gene_count > 0 today (post-2026-05-03 transport-arm fix); the future metabolomics-DM spec will introduce metabolites measured without any gene path, which will surface here with gene_count=0 — 0 ≠ 'absent from KG'.")
    organism_count: int = Field(default=0, description="Distinct organisms reaching this metabolite via any chemistry path (e.g. 31 for ATP). When > 0, narrow with organism_names filter.")
    transporter_count: int = Field(default=0, description="Distinct `tc_specificity` leaf TcdbFamily nodes annotated as transporting this metabolite (e.g. 17 for glucose, 229 for sodium). Scoped to leaves so the count reflects 'actual transporter systems' rather than counting ancestor families that inherit the substrate via the 2026-05-03 rollup. Source: TCDB-CAZy ontology.")
    evidence_sources: list[str] = Field(default_factory=list, description="Path provenance — values from {'metabolism', 'transport'}. 'metabolism' = at least one Reaction in KG involves this compound; 'transport' = at least one TcdbFamily curates this as substrate. 'metabolomics' is reserved for the future metabolomics-DM spec — no row carries it today. E.g. ['metabolism', 'transport'].")
    chebi_id: str | None = Field(default=None, description="ChEBI ID (raw numeric, e.g. '4167'). Populated on 90% of metabolites overall — 100% of the 452 chebi:-IDed transport-only metabolites (extracted from the ID itself), plus the kegg.compound:-IDed metabolites that cross-ref ChEBI.")
    pathway_ids: list[str] = Field(default_factory=list, description="KEGG pathway memberships (e.g. ['kegg.pathway:ko00010', 'kegg.pathway:ko01100']). Empty when no Metabolite_in_pathway edges. Drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...).")
    pathway_count: int = Field(default=0, description="Distinct count of KEGG pathways this metabolite is in (e.g. 5). Routing signal — when > 0, drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...) for genes annotated to those pathways. Equal to size(pathway_ids).")
    score: float | None = Field(default=None, description="Lucene relevance score (only with `search`).")

    # verbose
    inchikey: str | None = Field(default=None, description="InChIKey structural fingerprint (e.g. 'WQZGKKKJIJFFOK-GASJEMHNSA-N'). Verbose only.")
    smiles: str | None = Field(default=None, description="SMILES structural string (e.g. 'OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O'). Verbose only.")
    mnxm_id: str | None = Field(default=None, description="MetaNetX canonical ID (e.g. 'MNXM1364061'). Verbose only — populated on 100% of metabolites.")
    hmdb_id: str | None = Field(default=None, description="HMDB ID (e.g. 'HMDB0304632'). Verbose only — populated on 47%.")
    pathway_names: list[str] | None = Field(default=None, description="Pathway names aligned with pathway_ids (verbose only).")


class MetTopOrganism(BaseModel):
    organism_name: str = Field(description="Organism name (e.g. 'Ruegeria pomeroyi DSS-3')")
    count: int = Field(description="Number of matched metabolites this organism reaches (e.g. 1271)")


class MetTopPathway(BaseModel):
    pathway_id: str = Field(description="KEGG pathway ID (e.g. 'kegg.pathway:ko01100')")
    pathway_name: str = Field(description="Pathway name (e.g. 'Metabolic pathways')")
    count: int = Field(description="Number of matched metabolites in this pathway (e.g. 870)")


class MetEvidenceSourceBreakdown(BaseModel):
    evidence_source: str = Field(description="Evidence path (e.g. 'metabolism', 'transport')")
    count: int = Field(description="Number of matched metabolites with this evidence source (e.g. 1212). Sums to > total_matching when metabolites carry multiple sources.")


class MetXrefCoverage(BaseModel):
    with_chebi: int = Field(description="Matched metabolites with chebi_id (e.g. 1386)")
    with_hmdb: int = Field(description="Matched metabolites with hmdb_id (e.g. 849)")
    with_mnxm: int = Field(description="Matched metabolites with mnxm_id (e.g. 1563 — typically full coverage)")


class MetMassStats(BaseModel):
    mass_min: float | None = Field(default=None, description="Minimum mass across matched metabolites (e.g. 18.039). Null when no matched metabolite has a mass.")
    mass_median: float | None = Field(default=None, description="Median mass (e.g. 328.192).")
    mass_max: float | None = Field(default=None, description="Maximum mass (e.g. 5227.103).")


class MetNotFound(BaseModel):
    metabolite_ids: list[str] = Field(default_factory=list, description="Input metabolite_ids that don't exist in the KG (e.g. ['kegg.compound:C99999']).")
    organism_names: list[str] = Field(default_factory=list, description="Input organism_names with no matching OrganismTaxon (e.g. ['Bogus organism']).")
    pathway_ids: list[str] = Field(default_factory=list, description="Input pathway_ids with no matching KeggTerm (e.g. ['kegg.pathway:bogus']).")


class ListMetabolitesResponse(BaseModel):
    total_entries: int = Field(description="Total Metabolite nodes in KG (unfiltered, 3,025 today)")
    total_matching: int = Field(description="Metabolites matching filters")
    top_organisms: list[MetTopOrganism] = Field(default_factory=list, description="Top 10 organisms by metabolite count (within matched set), sorted desc")
    top_pathways: list[MetTopPathway] = Field(default_factory=list, description="Top 10 pathways by metabolite count (within matched set), sorted desc")
    by_evidence_source: list[MetEvidenceSourceBreakdown] = Field(default_factory=list, description="Frequency of evidence_sources values across matched set. Today: at most 2 entries (metabolism, transport).")
    xref_coverage: MetXrefCoverage = Field(description="Cross-ref ID coverage within matched set")
    mass_stats: MetMassStats = Field(description="Mass distribution within matched set")
    score_max: float | None = Field(default=None, description="Max Lucene score (only with search)")
    score_median: float | None = Field(default=None, description="Median Lucene score (only with search)")
    returned: int = Field(description="Metabolites in this response")
    offset: int = Field(default=0, description="Offset into full result set (e.g. 0)")
    truncated: bool = Field(description="True if total_matching > returned")
    not_found: MetNotFound = Field(default_factory=MetNotFound, description="Per-filter buckets for unknown input IDs")
    results: list[MetaboliteResult] = Field(default_factory=list)
```

### Wrapper

Mirrors `list_publications` shape: `await ctx.info(...)`, `try/except
ValueError → ToolError`. Build each sub-model from the api/ dict, then
the envelope:

```python
result = api.list_metabolites(
    search=search, metabolite_ids=metabolite_ids, ..., conn=conn,
)
results = [MetaboliteResult(**r) for r in result["results"]]
top_organisms = [MetTopOrganism(**b) for b in result["top_organisms"]]
top_pathways = [MetTopPathway(**b) for b in result["top_pathways"]]
by_evidence_source = [MetEvidenceSourceBreakdown(**b)
                      for b in result["by_evidence_source"]]
xref_coverage = MetXrefCoverage(**result["xref_coverage"])
mass_stats = MetMassStats(**result["mass_stats"])
not_found = MetNotFound(**result["not_found"])
return ListMetabolitesResponse(
    total_entries=result["total_entries"],
    total_matching=result["total_matching"],
    top_organisms=top_organisms,
    top_pathways=top_pathways,
    by_evidence_source=by_evidence_source,
    xref_coverage=xref_coverage,
    mass_stats=mass_stats,
    score_max=result.get("score_max"),
    score_median=result.get("score_median"),
    returned=result["returned"],
    offset=result.get("offset", 0),
    truncated=result["truncated"],
    not_found=not_found,
    results=results,
)
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildListMetabolites:
    test_no_filters
    test_metabolite_ids_filter
    test_kegg_compound_ids_filter
    test_chebi_ids_filter
    test_hmdb_ids_filter
    test_mnxm_ids_filter
    test_elements_filter_single                — assert ALL(... IN m.elements) clause
    test_elements_filter_multi                 — assert two-element AND
    test_mass_min_filter
    test_mass_max_filter
    test_mass_range_combined
    test_organism_names_filter                 — ANY(o IN coalesce(m.organism_names, [])
                                                 WHERE toLower(o) IN $organism_names_lc)
    test_pathway_ids_filter                    — ANY(p IN coalesce(m.pathway_ids, [])
                                                 WHERE p IN $pathway_ids)
    test_evidence_sources_filter               — ANY(s IN $evidence_sources
                                                 WHERE s IN m.evidence_sources)
    test_combined_filters
    test_search_uses_fulltext_entrypoint
    test_returns_compact_columns               — RETURN list matches spec exactly
                                                 (incl. pathway_ids + pathway_count)
    test_returns_verbose_columns               — verbose adds inchikey, smiles,
                                                 mnxm_id, hmdb_id, pathway_names
                                                 (all property reads on m)
    test_verbose_has_no_call_subqueries        — guard against re-introducing
                                                 per-row edge traversals; verbose
                                                 stays 100% property reads
    test_order_by                              — ORDER BY m.organism_count DESC,
                                                 m.gene_count DESC, m.id
    test_order_by_with_search                  — ORDER BY score DESC,
                                                 m.organism_count DESC, m.id
    test_limit_and_offset_clauses
    test_per_row_pathway_count_is_property_read — coalesce(m.pathway_count, 0) AS pathway_count
    test_no_edge_traversal_in_filters          — confirms NO `EXISTS { MATCH ... }`
                                                 against Metabolite_in_pathway or
                                                 Organism_has_metabolite (guards against
                                                 a regression to the pre-KG-A5..A8 form)

class TestBuildListMetabolitesSummary:
    test_no_filters
    test_with_filters
    test_shares_where_clause
    test_returns_envelope_columns              — total_entries, total_matching,
                                                 top_organisms, top_pathways,
                                                 by_evidence_source, xref counts, mass stats
    test_does_not_collect_metabolite_nodes     — guards memory-friendly refactor:
                                                 assert no `collect(m) AS matched`
                                                 (should flatten m.organism_names /
                                                  m.pathway_ids instead)
    test_top_organisms_uses_apoc_frequencies   — assert pattern
                                                 `apoc.coll.frequencies(all_orgs)` +
                                                 `UNWIND ... ORDER BY ... DESC LIMIT 10`
    test_top_pathways_uses_keggterm_lookup     — assert OPTIONAL MATCH (p:KeggTerm)
                                                 inside the CALL for pathway_name
    test_search_adds_score_columns             — score_max via apoc.coll.max,
                                                 score_median via apoc.coll.sort + index
```

### Unit: API function (`test_api_functions.py`)

```
class TestListMetabolites:
    test_returns_dict_envelope
    test_summary_only_when_summary_true
    test_lucene_retry_on_parse_error
    test_evidence_sources_enum_validation
    test_search_empty_validation
    test_organism_names_lowercased
    test_not_found_metabolite_ids
    test_not_found_organism_names
    test_not_found_pathway_ids
    test_sparse_strip_null_chebi
    test_verbose_returns_only_property_reads   — guard against future regression
                                                 reintroducing CALL subqueries
    test_creates_conn_when_none
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestListMetabolitesWrapper:
    test_returns_response_type
    test_compact_fields_present
    test_verbose_fields_optional
    test_not_found_structure          — typed dict with all 3 keys
    test_envelope_breakdowns_present
    test_params_forwarded
    test_validation_error_raises_tool_error
```

Update `EXPECTED_TOOLS` to include `list_metabolites`.

### Integration (`test_mcp_tools.py`)

Live-KG smoke cases:
- `list_metabolites()` → total_matching == 3,025
- `list_metabolites(elements=["N"])` → 1,563
- `list_metabolites(elements=["N", "P"])` → 556
- `list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"])`
  → 804
- `list_metabolites(pathway_ids=["kegg.pathway:ko00910"])` → 18
- `list_metabolites(metabolite_ids=["kegg.compound:C00031", "kegg.compound:C99999"])`
  → 1 result, `not_found.metabolite_ids == ["kegg.compound:C99999"]`
- `list_metabolites(search="glucose")` → ≥1 result with `score`
- `list_metabolites(evidence_sources=["transport"])` → 1,097
- `list_metabolites(summary=True)` → results=[], envelope populated

### Integration: API contract (`test_api_contract.py`)

Snapshot the envelope + per-row schema. Updates whenever return shape
changes.

### Regression (`test_regression.py` + `test_eval.py`)

Add to both `TOOL_BUILDERS` dicts:
```python
"list_metabolites": build_list_metabolites,
```

Generate new baselines via `pytest tests/regression/ --force-regen -m kg
-k list_metabolites` after Phase 2 build.

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: list_metabolites_all
  tool: list_metabolites
  desc: All metabolites returned when no filters
  params: {}
  expect:
    min_rows: 1
    columns: [metabolite_id, name, formula, elements, gene_count,
              organism_count, transporter_count, evidence_sources, pathway_ids]

- id: list_metabolites_n_elements
  tool: list_metabolites
  desc: N-bearing metabolites filter
  params: {elements: [N]}
  expect:
    min_rows: 1

- id: list_metabolites_pathway
  tool: list_metabolites
  desc: Pathway membership filter (nitrogen metabolism)
  params: {pathway_ids: [kegg.pathway:ko00910]}
  expect:
    min_rows: 1

- id: list_metabolites_med4_n
  tool: list_metabolites
  desc: MED4 + N elements (the N-source workflow primitive)
  params: {organism_names: [Prochlorococcus MED4], elements: [N]}
  expect:
    min_rows: 1

- id: list_metabolites_search_glucose
  tool: list_metabolites
  desc: Lucene search by name
  params: {search: glucose}
  expect:
    min_rows: 1
    columns: [metabolite_id, name, score]

- id: list_metabolites_id_batch_with_unknown
  tool: list_metabolites
  desc: Batch IDs with unknown — populates not_found.metabolite_ids
  params: {metabolite_ids: [kegg.compound:C00031, kegg.compound:C99999]}
  expect:
    min_rows: 1
```

---

## About Content

**File:** `multiomics_explorer/inputs/tools/list_metabolites.yaml`

```yaml
examples:
  - title: All N-bearing metabolites in MED4 (the N-source workflow primitive)
    call: list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=5)

  - title: Pathway-anchored — metabolites in nitrogen metabolism
    call: list_metabolites(pathway_ids=["kegg.pathway:ko00910"], limit=10)

  - title: Cross-organism survey — metabolites both partners reach
    call: list_metabolites(organism_names=["Prochlorococcus MED4", "Alteromonas macleodii MIT1002"], summary=True)

  - title: Lucene search by name
    call: list_metabolites(search="glucose", limit=3)

  - title: Transport-only metabolites (TCDB-curated substrates without local catalysis)
    call: list_metabolites(evidence_sources=["transport"], summary=True)

  - title: Multi-step — find N-metabolites then drill into catalysts
    steps: |
      Step 1: list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=10)
              → extract metabolite_ids of interest

      Step 2: genes_by_metabolite(metabolite_ids=[chosen_ids], organism="Prochlorococcus MED4")
              → catalysing genes per metabolite

verbose_fields:
  - inchikey
  - smiles
  - mnxm_id
  - hmdb_id
  - pathway_names

chaining:
  - "list_organisms (per-row metabolite_count > 0) → list_metabolites(organism_names=[...])"
  - "list_metabolites → genes_by_metabolite(metabolite_ids=[...], organism=...)"
  - "list_metabolites (per-row pathway_ids) → genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...)"
  - "differential_expression_by_gene → gene_metabolic_role(metabolite_elements=['N']) → list_metabolites for chemistry context"

mistakes:
  - "Direction-agnostic. Joining through Reaction_has_metabolite (catalysis) and Tcdb_family_transports_metabolite (transport) does NOT distinguish substrates from products. KEGG equation order is arbitrary. Layer DE direction (`differential_expression_by_gene`) and functional annotation to disambiguate."
  - "elements is presence-only, AND-of. ['N','P'] requires BOTH N and P to be present. Use the `elements` filter — never substring-match on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N')."
  - "gene_count = 0 does not mean the metabolite is absent from the KG. As of the 2026-05-03 transport-arm fix every Metabolite has gene_count > 0; the future metabolomics-DM spec will reintroduce gene_count=0 (measured-only metabolites with no gene path)."
  - "organism_names with multiple values is UNION, not intersection. To find metabolites BOTH organisms reach, run two single-org calls and intersect by metabolite_id (or filter per-row by organism_count and inspect `m.organism_names` for the full UNION list)."
  - "metaboliteFullText covers Metabolite.name only — NOT formula. For element/composition queries, use `elements` (presence list)."
  - "evidence_sources accepts 'metabolomics' as forward-compat for the future metabolomics-DM spec; no row matches it today."
  - wrong: "list_metabolites(elements=['N'], gene_count_min=1)  # gene_count_min isn't a param"
    right: "list_metabolites(elements=['N'])  # then filter rows in code by gene_count > 0"
  - wrong: "list_metabolites(organism_names=['MED4'])  # short name doesn't match"
    right: "list_metabolites(organism_names=['Prochlorococcus MED4'])  # full preferred_name"
```

Then build:

```bash
uv run python scripts/build_about_content.py list_metabolites
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add `list_metabolites` row to MCP Tools table — "Discover/filter metabolites in the chemistry layer (incl. TCDB transport substrates). Filterable by elements, mass, organism_names, pathway_ids, evidence_sources, plus xref ID batch input. Rich envelope (top_organisms, top_pathways, by_evidence_source, xref_coverage, mass_stats) and per-row routing (gene_count, transporter_count → drill-down tools)." |

---

## Forward-compatibility notes

- **TCDB-CAZy is live today** — no remaining forward-compat slots for
  `evidence_sources='transport'` or `transporter_count`. Code is written
  against today's KG, not tomorrow's.
- **Metabolomics-DM (no spec yet)** — `evidence_sources='metabolomics'` is
  accepted as a filter value but no row carries it; pure-metabolomics
  metabolites will surface in `list_metabolites` with `gene_count=0`,
  `transporter_count=0`, `evidence_sources=['metabolomics']` once that
  KG-side spec lands. No explorer change needed at that point — only the
  field description's example values may want a refresh.
- **`KeggTerm.reaction_count` / `metabolite_count` rollups** are populated
  on the live KG (KG-A4 landed) but **not consumed in slice 1** — Tier-2
  follow-up extends `MetTopPathway` with these. Spec'd separately.

## Open questions / risks

- **Retroactive `top_*` rename for `list_organisms.by_metabolic_capability`?**
  This spec introduces the project convention: `top_*` for hardcoded top-N
  rollups, `by_*` for full frequency rollups. The already-shipped
  `list_organisms.by_metabolic_capability` is a top-10 rollup — rename
  it to `top_metabolically_capable_organisms` (or similar) for
  consistency? Not blocking slice-1 build; can ship as a one-line
  follow-up renamer (with regression baseline regen + a single about-content
  rebuild). Recommendation: yes, do it as a small follow-up PR after this
  spec lands so the convention is uniform across the chemistry surface.
- **Envelope `top_organisms` rollup uses `m.organism_names`.** That
  property is UNION'd post-TCDB (metabolism + transport), so the `count`
  field reflects "matched metabolites this organism reaches by ANY
  chemistry path." For per-organism per-path split + per-gene detail,
  the LLM drills into `genes_by_metabolite` (slice-1 Tool #2).
- **Search index excludes formula.** Slice-1 design said it covered
  `name + formula`. Live state shows `name` only. Mitigation: docs
  steer composition queries to `elements` (which is the right primitive
  anyway). Filed as an issue if the KG team wants to extend the index
  later — out of slice 1 scope.
- **ID prefixes.** Today only `kegg.compound:` and `chebi:`. The slice-1
  design hinted at `mnx:` IDs; verifying showed no `mnx:` prefixed IDs
  in the KG (everything resolves through to `kegg.compound:` or `chebi:`).
  No code change needed; spec corrected.

### Resolved

- **KG-A5..A8 timing — RESOLVED:** all 4 follow-up asks landed
  2026-05-02 (verified live). Spec uses the rollup-based Cypher
  directly; no fallback branch needed. `_USE_METABOLITE_ROLLUPS`
  flag and helper functions are not in the build.
- **`chebi_id` on chebi:-prefixed metabolites — RESOLVED:** all 452
  populated as a separate property (the numeric portion of the ID).
  No api/-side parse fallback needed. Field description updated.
- **`evidence_sources` typing — RESOLVED:** wrapper uses
  `list[Literal["metabolism", "transport", "metabolomics"]]`. Pydantic
  Literal validation at the MCP boundary; api/ layer mirror-validates
  for non-MCP callers. Per field-rubric: "Use Literal[...] for params
  with fixed valid values known at code time" — the open-ended
  rationale was overruled in favor of MCP-boundary safety.
- **KG-A9 / KG-A10 indexes — RESOLVED:** `kegg_term_id_idx` (RANGE
  on KeggTerm.id) and `metabolite_hmdb_idx` (RANGE on
  Metabolite.hmdb_id) both LANDED 2026-05-03 (verified ONLINE via
  `SHOW INDEXES`). Summary `top_pathways` KeggTerm lookup is now an
  index seek; `hmdb_ids` filter has sibling-index parity with
  chebi/kegg/mnxm. No remaining KG-side dependencies for Phase 2.

## References

- Slice-1 parent design: `docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md` § 2.1
- KG-side asks (chemistry slice 1 direct asks A1..A4 — all landed): `docs/superpowers/specs/2026-05-01-kg-side-chemistry-slice1-asks.md`
- KG-side follow-up asks (A5..A8 — landed 2026-05-02): `docs/superpowers/specs/2026-05-02-kg-side-chemistry-slice1-followup-asks.md`
- TCDB-CAZy ontology (live): `multiomics_biocypher_kg/docs/kg-changes/tcdb-cazy-ontologies.md`
- Closest pattern peers: `docs/tool-specs/list_publications.md`, `docs/tool-specs/list_derived_metrics.md`
- Sibling extension (already shipped): `docs/tool-specs/list_organisms_chemistry.md`
- Add-or-update-tool checklist: `.claude/skills/add-or-update-tool/references/checklist.md`
- Field-design rubric: `.claude/skills/add-or-update-tool/references/field-rubric.md`
