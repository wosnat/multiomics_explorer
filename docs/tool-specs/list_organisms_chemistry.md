# list_organisms — Chemistry rollup extension — What to Change

## Executive Summary

Surface the two `OrganismTaxon` chemistry rollups landed by the chemistry-slice-1 KG asks (KG-A2 / KG-A4-adjacent — they were already on `OrganismTaxon` from Phase 1.2 chemistry layer; verified live 2026-05-02): `reaction_count` and `metabolite_count`. Adds a small envelope rollup `by_metabolic_capability` listing top-N organisms by metabolite breadth.

This is the **smallest 4-layer pass in chemistry slice 1** — KG props are already populated, no new builder logic, two new fields plus one envelope key.

Purpose: gives the LLM a per-organism chemistry-coverage signal at the discovery entry point, mirroring how `gene_count` / `experiment_count` already function as routing indicators.

## Out of Scope

- **Filter on `reaction_count` / `metabolite_count`** (e.g. `min_reaction_count: int`). Defer until a real workflow demands it; LLM can sort client-side from returned rows.
- **Top-N tunable.** `by_metabolic_capability` returns top 10 fixed. Add `top_n` param later if needed.
- **Pathway-level rollups** (`KeggTerm.reaction_count` / `metabolite_count`, also landed via KG-A4). Those surface in a Tier-2 follow-up extension to `list_metabolites.by_pathway`, not this PR.
- **Transport path additions** (TCDB-CAZy `transporter_count`, `evidence_sources`). On `Metabolite`, not `OrganismTaxon`. Not relevant here.

## Status / Prerequisites

- [x] Scope reviewed with user (chemistry slice-1 design doc, Section 2.4)
- [x] No new KG schema changes — both rollups already populated on `OrganismTaxon` (verified live 2026-05-02: 31 of 36 organisms have non-zero values; max 1,490 metabolites)
- [x] Cypher verified against live KG (see "KG verification" below)
- [x] Result-size controls decided: no new structural params; match existing `summary` / `verbose` / `limit` semantics
- [ ] Ready for Phase 2 (build) — pending user approval of this spec

## Use cases

- **Discovery routing:** `list_organisms()` returns `metabolite_count` per row; LLM uses it to identify chemistry-rich organisms before drilling in via `list_metabolites(organism_names=[...])` (slice-1 sibling tool).
- **Comparison:** `list_organisms(organism_names=[...])` for two organisms shows side-by-side metabolic capability counts. Useful for cross-feeding hypothesis framing.
- **Survey:** `summary=True` returns `by_metabolic_capability` showing which organisms have richest chemistry coverage, without paging through detail rows.

## KG dependencies

No schema changes. Reads two existing properties on `OrganismTaxon`:

- `reaction_count: int` — already populated post-import (chemistry layer Phase 1.2)
- `metabolite_count: int` — already populated post-import (chemistry layer Phase 1.2)

Both default to 0 for organisms without chemistry coverage (5 of 36 organisms — typically `treatment` or `reference_proteome_match` types without genes).

---

## Tool Signature (after change)

**No new params.** Existing signature unchanged.

**Return envelope (after change):**

```python
class ListOrganismsResponse(BaseModel):
    total_entries: int
    total_matching: int
    by_cluster_type: list[OrgClusterTypeBreakdown]
    by_organism_type: list[OrgTypeBreakdown]
    by_value_kind: list[OrgValueKindBreakdown]
    by_metric_type: list[OrgMetricTypeBreakdown]
    by_compartment: list[OrgCompartmentBreakdown]
    by_metabolic_capability: list[OrgMetabolicCapabilityBreakdown]    # NEW
    returned: int
    offset: int
    truncated: bool
    not_found: list[str]
    results: list[OrganismResult]
```

**Per-row `OrganismResult` (after change):**

Adds two compact fields. No verbose-only additions.

```python
class OrganismResult(BaseModel):
    # ... existing fields ...
    reaction_count: int = Field(default=0, description="...")          # NEW
    metabolite_count: int = Field(default=0, description="...")        # NEW
```

| Envelope/row field | Before | After |
|---|---|---|
| `OrganismResult.reaction_count` | absent | int (default 0); compact |
| `OrganismResult.metabolite_count` | absent | int (default 0); compact |
| `by_metabolic_capability` | absent | list of top-10 organisms by metabolite_count, with reaction_count alongside |

## Result-size controls

Unchanged. KG still has only ~36 organisms; result fits in one response easily. Existing `summary` / `verbose` / `limit` semantics carry over verbatim.

## Special handling

- **`coalesce(o.reaction_count, 0)` / `coalesce(o.metabolite_count, 0)`** in the builder. Even though all current organisms have the props populated, the coalesce keeps the explorer code timing-resilient — works against any KG that hasn't yet shipped chemistry rollups.
- **`by_metabolic_capability` computed in api/, not Cypher.** The detail builder already returns per-row `reaction_count` / `metabolite_count` (after this change), so api/ can sort + slice for the top-N rollup without re-querying. Avoids inflating the Cypher summary builder. Filter to non-zero rows so organisms without chemistry don't pollute the rollup.
- **When `summary=True`**: detail rows aren't fetched, so api/ runs a small standalone query (the same Cypher as the detail builder, projecting only the 3 fields) to populate `by_metabolic_capability`. Adds one query when `summary=True` AND chemistry coverage is requested. Cheap (≤36 row scan).
- **When `total_matching == 0`**: `by_metabolic_capability == []`. No special-case needed.

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | Append `coalesce(o.reaction_count, 0)` and `coalesce(o.metabolite_count, 0)` to `build_list_organisms` compact RETURN. |
| 2 | API function | `api/functions.py` | Compute `by_metabolic_capability` from matched rows (or run small extra query when `limit=0`); add to envelope. |
| 3 | MCP wrapper | `mcp_server/tools.py` | Add `reaction_count` and `metabolite_count` to `OrganismResult`. Add `OrgMetabolicCapabilityBreakdown` model and `by_metabolic_capability` to `ListOrganismsResponse`. Wire pass-through in wrapper. |
| 4 | Unit tests | `tests/unit/test_query_builders.py` | Extend `TestBuildListOrganisms`: assert new RETURN columns present. |
| 5 | Unit tests | `tests/unit/test_api_functions.py` | Extend `TestListOrganisms`: `reaction_count`/`metabolite_count` propagate to results; `by_metabolic_capability` computed correctly (sorted desc by metabolite_count, top 10, non-zero filter); summary=True path hits the small-query branch. |
| 6 | Unit tests | `tests/unit/test_tool_wrappers.py` | Extend `TestListOrganismsWrapper`: assert new envelope key + new row fields surface. |
| 7 | Integration | `tests/integration/test_mcp_tools.py` | Live-KG case: `list_organisms(organism_names=["Prochlorococcus MED4", "Alteromonas macleodii EZ55"])` → both rows have `metabolite_count > 0`, `by_metabolic_capability` includes both ordered by metabolite_count desc. |
| 8 | Regression | `tests/regression/test_regression.py` | Regenerate baselines with `--force-regen -m kg` (new RETURN columns will fail existing baselines). |
| 9 | About content | `inputs/tools/list_organisms.yaml` | Add example with `metabolite_count`/`reaction_count`. Add chaining note: "list_organisms → list_metabolites(organism_names=[...]) when metabolite_count > 0". Run `build_about_content.py`. |
| 10 | Docs | `CLAUDE.md` | Update `list_organisms` row to mention chemistry-coverage rollups + `by_metabolic_capability` envelope. |

---

## Query Builder

**File:** `kg/queries_lib.py` (line 1050 `build_list_organisms`)

### `build_list_organisms` (updated)

Append two `coalesce(...)` lines to the compact RETURN. No filter, signature, or summary-builder changes.

```cypher
MATCH (o:OrganismTaxon)
WHERE ($organism_names_lc IS NULL
       OR toLower(o.preferred_name) IN $organism_names_lc)
  AND <existing compartment filter>
RETURN o.preferred_name AS organism_name,
       o.organism_type AS organism_type,
       o.genus AS genus,
       o.species AS species,
       o.strain_name AS strain,
       o.clade AS clade,
       o.ncbi_taxon_id AS ncbi_taxon_id,
       o.gene_count AS gene_count,
       o.publication_count AS publication_count,
       o.experiment_count AS experiment_count,
       o.treatment_types AS treatment_types,
       coalesce(o.background_factors, []) AS background_factors,
       o.omics_types AS omics_types,
       coalesce(o.clustering_analysis_count, 0) AS clustering_analysis_count,
       coalesce(o.cluster_types, []) AS cluster_types,
       coalesce(o.derived_metric_count, 0) AS derived_metric_count,
       coalesce(o.derived_metric_value_kinds, []) AS derived_metric_value_kinds,
       coalesce(o.compartments, []) AS compartments,
       coalesce(o.reaction_count, 0) AS reaction_count,        -- NEW
       coalesce(o.metabolite_count, 0) AS metabolite_count,    -- NEW
       o.reference_database AS reference_database,
       o.reference_proteome AS reference_proteome,
       coalesce(o.growth_phases, []) AS growth_phases
       {verbose_columns}
ORDER BY o.genus, o.preferred_name
```

`build_list_organisms_summary` is **not modified.** `by_metabolic_capability` is computed in api/ from the matched detail rows (or via a small extra Cypher when `summary=True`).

### KG verification (verified 2026-05-02)

| Query | Expected | Actual | Pass |
|---|---|---|---|
| `coalesce(o.reaction_count, 0)` populated for known organism | MED4 → 943, EZ55 → 1348 | 943 / 1348 | ✓ |
| `coalesce(o.metabolite_count, 0)` populated | MED4 → 1039, EZ55 → 1428 | 1039 / 1428 | ✓ |
| Top organism by metabolite_count | P. putida KT2440 (1490) | 1490 | ✓ |
| Organism count with non-zero chemistry | 31 / 36 | 31 / 36 | ✓ |
| Filter by 2 organisms returns chemistry on both rows | both > 0 | ✓ | ✓ |

---

## API Function

**File:** `api/functions.py` (line 609 `list_organisms`)

Add `by_metabolic_capability` computation. Two paths:

1. **`limit > 0`:** detail query returns matched rows with `reaction_count`/`metabolite_count` columns. Sort by `metabolite_count` desc, filter to non-zero, slice to top 10.

2. **`limit == 0` (summary mode):** detail query is skipped today. Run a small extra query (same WHERE as detail builder, projecting only the 3 fields) just to populate `by_metabolic_capability`.

```python
# After existing detail-fetch block:
if matched:
    chemistry_capable = [
        {
            "organism_name": r["organism_name"],
            "reaction_count": r.get("reaction_count", 0),
            "metabolite_count": r.get("metabolite_count", 0),
        }
        for r in matched
        if r.get("metabolite_count", 0) > 0 or r.get("reaction_count", 0) > 0
    ]
    chemistry_capable.sort(key=lambda r: r["metabolite_count"], reverse=True)
    by_metabolic_capability = chemistry_capable[:10]
else:
    by_metabolic_capability = []

# When limit == 0 and chemistry-capable rows still wanted:
if limit == 0 and total_matching > 0:
    capability_cypher = build_list_organisms(
        organism_names_lc=names_lc, compartment=compartment, verbose=False,
    )[0]
    capability_rows = conn.execute_query(capability_cypher, **detail_params)
    chemistry_capable = [
        {
            "organism_name": r["organism_name"],
            "reaction_count": r.get("reaction_count", 0),
            "metabolite_count": r.get("metabolite_count", 0),
        }
        for r in capability_rows
        if r.get("metabolite_count", 0) > 0 or r.get("reaction_count", 0) > 0
    ]
    chemistry_capable.sort(key=lambda r: r["metabolite_count"], reverse=True)
    by_metabolic_capability = chemistry_capable[:10]
```

(The duplication in the two branches is acceptable — small block, clearer than refactoring. If it grows, extract a helper.)

Add `by_metabolic_capability` to the returned dict. Update docstring to document the new envelope key + per-row fields.

---

## MCP Wrapper

**File:** `mcp_server/tools.py` (line 462 `OrganismResult` and surrounding models)

### Pydantic — `OrganismResult` (extended)

Insert in the **compact** field block (after `compartments`, before `reference_database`):

```python
reaction_count: int = Field(
    default=0,
    description="Distinct reactions catalyzed by genes in this organism (e.g. 943). "
    "When > 0, drill in via list_metabolites(organism_names=[organism_name]) to enumerate "
    "metabolites this organism is capable of metabolizing.",
)
metabolite_count: int = Field(
    default=0,
    description="Distinct metabolites reachable via Organism_has_metabolite (e.g. 1039). "
    "Capability signal — does NOT mean these metabolites were measured. "
    "When TCDB-CAZy ships, this count will grow to include transport-substrate metabolites.",
)
```

### Pydantic — new breakdown model

```python
class OrgMetabolicCapabilityBreakdown(BaseModel):
    organism_name: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
    reaction_count: int = Field(description="Distinct reactions catalyzed by this organism's genes (e.g. 943)")
    metabolite_count: int = Field(description="Distinct metabolites reachable via gene catalysis (e.g. 1039)")
```

### Pydantic — `ListOrganismsResponse` (extended)

Insert after `by_compartment`:

```python
by_metabolic_capability: list[OrgMetabolicCapabilityBreakdown] = Field(
    default_factory=list,
    description="Top 10 organisms by metabolite_count (within matched set), sorted desc. "
    "Filter excludes organisms with zero chemistry. [] when no matched organism has chemistry.",
)
```

### Wrapper

Pass-through in the wrapper body — one new line in the response construction:

```python
by_metabolic_capability = [
    OrgMetabolicCapabilityBreakdown(**b)
    for b in result.get("by_metabolic_capability", [])
]
# ... in ListOrganismsResponse(...):
by_metabolic_capability=by_metabolic_capability,
```

Docstring: append a brief note about the new chemistry-coverage signal and drill-down to `list_metabolites`.

---

## Tests

### Unit: query builder (extend `TestBuildListOrganisms`)

```
test_returns_reaction_count_column      — RETURN includes "coalesce(o.reaction_count, 0) AS reaction_count"
test_returns_metabolite_count_column    — RETURN includes "coalesce(o.metabolite_count, 0) AS metabolite_count"
```

### Unit: API function (extend `TestListOrganisms`)

```
test_reaction_count_propagates_to_results
test_metabolite_count_propagates_to_results
test_by_metabolic_capability_sorted_desc_by_metabolite_count
test_by_metabolic_capability_excludes_zero_chemistry
test_by_metabolic_capability_top_10_cap
test_by_metabolic_capability_summary_mode_runs_extra_query  — limit=0 path computes via small Cypher
test_by_metabolic_capability_empty_when_no_matches
```

### Unit: MCP wrapper (extend `TestListOrganismsWrapper`)

```
test_response_has_by_metabolic_capability
test_organism_result_has_reaction_count_and_metabolite_count
test_by_metabolic_capability_passes_through
```

`EXPECTED_TOOLS` already lists `list_organisms` — no change needed.

### Integration (`test_mcp_tools.py`)

Live-KG case (re-uses 2026-05-02 verified data):
- `list_organisms(organism_names=["Prochlorococcus MED4", "Alteromonas macleodii EZ55"])`
  → both rows have `metabolite_count` and `reaction_count` > 0
  → `by_metabolic_capability` includes both, sorted with EZ55 (1428) first, MED4 (1039) second.

### Regression (`test_regression.py`)

The new RETURN columns will fail existing baselines. Regenerate:

```bash
pytest tests/regression/ --force-regen -m kg
```

`TOOL_BUILDERS["list_organisms"]` already wired to `build_list_organisms` — no change needed unless the call signature changes (it doesn't).

### Eval cases (`tests/evals/cases.yaml`)

Add a small case: query MED4 + assert `metabolite_count > 0` and `by_metabolic_capability[0].metabolite_count >= [...]`.

---

## About Content

**File:** `multiomics_explorer/inputs/tools/list_organisms.yaml`

Add example:

```yaml
- title: Identify chemistry-rich organisms (capability ranking)
  call: list_organisms(summary=True)
  response: |
    {"total_entries": 36, "total_matching": 36, "by_metabolic_capability": [
       {"organism_name": "Pseudomonas putida KT2440", "reaction_count": 1449, "metabolite_count": 1490},
       {"organism_name": "Ruegeria pomeroyi DSS-3", "reaction_count": 1377, "metabolite_count": 1468},
       {"organism_name": "Alteromonas macleodii EZ55", "reaction_count": 1348, "metabolite_count": 1428}
     ], "returned": 0, "truncated": true, ...}
```

Add to existing `chaining`:

```yaml
- "list_organisms (per-row metabolite_count > 0) → list_metabolites(organism_names=[...]) for chemistry drill-down"
```

Add to existing `mistakes`:

```yaml
- "metabolite_count counts capability via gene catalysis — distinct metabolites reachable through Gene → Reaction → Metabolite. Does not include transport substrates (until TCDB-CAZy ships) or measured metabolites (until metabolomics-DM ships). 0 does not mean the metabolite is absent from the KG."
```

Then regenerate:

```bash
uv run python scripts/build_about_content.py list_organisms
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Update `list_organisms` row: mention `reaction_count` / `metabolite_count` per row + `by_metabolic_capability` envelope rollup. |

---

## Forward-compatibility notes

When the TCDB-CAZy spec lands and extends `Metabolite.gene_count` / `Organism_has_metabolite` to UNION the transport path, `OrganismTaxon.metabolite_count` will grow to include transport substrates. **No explorer change needed** — the value just gets bigger. The Pydantic field description already states this.

When the metabolomics-DM spec lands, it does NOT change `OrganismTaxon.metabolite_count` (metabolomics-only metabolites have no gene path). `by_metabolic_capability` continues to reflect catalysis + transport coverage; metabolomics adds a separate axis surfaced through `list_metabolites` rather than `list_organisms`.

## References

- Chemistry slice-1 design (parent): `docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md` § 2.4
- KG-side asks: `docs/superpowers/specs/2026-05-01-kg-side-chemistry-slice1-asks.md`
- Existing tool spec (organism_names filter, prior change): `docs/tool-specs/list_organisms_changes.md`
- Canonical tool spec: `docs/tool-specs/list_organisms.md`
