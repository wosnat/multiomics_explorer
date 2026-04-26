# list_organisms: Add `organism_names` filter — What to Change

## Executive Summary

Add a batch filter parameter to `list_organisms` so callers can fetch a
specific set of organisms by exact name. Mirrors the `publication_dois`
shape on `list_publications`.

The current tool returns all ~32 organisms in the KG. Callers wanting
a subset must pull everything and filter client-side, or fall back to
`run_cypher`. After this change, `list_organisms(organism_names=[...])`
returns only the matched rows with a `not_found` envelope for unknown
inputs.

## Out of Scope

- **Partial matching** (e.g. `"MED4"` → `"Prochlorococcus MED4"`).
  Callers must pass exact `preferred_name` values. Add later if needed.
- **`genus` / `clade` / `strain_name` filters.** "Give me all
  Prochlorococcus" is a real use case but deferred. Add later if needed.
- **`ncbi_taxon_id` filter.** Sparse on non-genome rows; defer.
- **Lucene `search_text`.** No `organismTaxonFullText` index exists;
  adding one requires a KG-side schema change. Defer.

## Status / Prerequisites

- [x] Scope reviewed with user
- [x] No KG schema changes needed
- [x] Cypher verified against live KG (see "KG verification" below)
- [x] Result-size controls decided: add `summary` flag to match
      ID-list-tool convention; existing `verbose` and `limit` retained
- [x] Ready for Phase 2 (build)

## Use cases

- **Targeted lookup:** "Give me data-availability for these specific
  organisms" — caller already has canonical names from a prior
  `list_organisms` call or another tool's response.
- **Round-tripping:** validate that a list of names all resolve to
  real organisms (`not_found` reports any that don't).
- **Chaining:** other tools return `organism_name` columns →
  `list_organisms(organism_names=...)` to enrich with gene/publication
  counts and treatment types.

## KG dependencies

No schema changes. Reuses existing properties on `OrganismTaxon`:
`preferred_name`, plus the precomputed stats already returned today.

---

## Tool Signature (after change)

```python
@mcp.tool(
    tags={"organisms", "discovery"},
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def list_organisms(
    ctx: Context,
    organism_names: Annotated[list[str] | None, Field(
        description="Filter by exact organism preferred_name (case-insensitive). "
        "Pass values from a prior list_organisms call. Unknown names "
        "are reported in not_found.",
    )] = None,
    summary: Annotated[bool, Field(
        description="Return summary fields only (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include full taxonomy hierarchy "
        "(family, order, class, phylum, kingdom, superkingdom, lineage).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
    offset: Annotated[int, Field(
        description="Number of results to skip for pagination.", ge=0,
    )] = 0,
) -> ListOrganismsResponse:
    ...
```

**Return envelope (after change):**
`{total_entries, total_matching, by_cluster_type, by_organism_type,
returned, offset, truncated, not_found, results: [...]}`

| Envelope field | Before | After |
|---|---|---|
| `total_entries` | total in KG | unchanged — total in KG |
| `total_matching` | absent | count after filter (`= total_entries` when filter is None) |
| `not_found` | absent | input names that didn't match any organism, original casing preserved; `[]` when filter is None |
| `by_cluster_type` / `by_organism_type` | KG-wide breakdowns | breakdowns over the matched set when filter applied; KG-wide otherwise |
| `truncated` | `total_entries > offset + returned` | `total_matching > offset + returned` |
| `results` rows, `returned`, `offset` | unchanged | unchanged |

## Result-size controls

### Option A: Small result set (no detail/summary modes needed)

KG holds ~32 `OrganismTaxon` nodes. Filtering can only shrink that.
No pagination of large result sets, but we do add the standard `summary`
flag because this is now a batch-input tool.

**Sort key:** `genus ASC, preferred_name ASC` (unchanged).

**Default limit:** 5 (unchanged).

**Verbose:** unchanged. Compact vs verbose column split is identical
to today.

**Summary flag:** `summary=True` → `results=[]`, summary fields populated
(sugar for `limit=0`).

## Special handling

- **No caching.** Query reads precomputed properties from ≤32 nodes.
- **Case-insensitive match.** Caller-typed names compared via
  `toLower(preferred_name) IN $organism_names_lc`. The api/ layer
  lowercases the input list once before passing it to Cypher.
- **`not_found` is computed in api/** via a separate small Cypher query
  (mirrors `list_publications`). Original input casing is preserved in
  the returned `not_found` list.
- **Summary breakdowns reflect filtered set** when filter is applied —
  computed in api/ from the matched rows (same in-memory pattern as
  today, just operating on the filtered list).

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | Update `build_list_organisms` — accept `organism_names_lc`, add WHERE. Add new `build_list_organisms_summary` for unfiltered KG-wide count. |
| 2 | API function | `api/functions.py` | Add `organism_names`, `summary` params. Wire `total_matching`, `not_found`, breakdowns over filtered set, truncated semantics. |
| 3 | MCP wrapper | `mcp_server/tools.py` | Add `organism_names` and `summary` params with `Annotated[..., Field(...)]`. Add `total_matching: int` and `not_found: list[str]` to `ListOrganismsResponse`. |
| 4 | Unit tests | `tests/unit/test_query_builders.py` | Extend `TestBuildListOrganisms`: filter WHERE clause, params, summary builder. |
| 5 | Unit tests | `tests/unit/test_api_functions.py` | Extend `TestListOrganisms`: filter forwarding, not_found, summary flag, total_matching. |
| 6 | Unit tests | `tests/unit/test_tool_wrappers.py` | Extend `TestListOrganismsWrapper`: new envelope fields, batch filter call. |
| 7 | Integration | `tests/integration/test_mcp_tools.py` | Live-KG case: filter by 2 known names + 1 unknown → `not_found` populated. |
| 8 | Regression | `tests/regression/test_regression.py` | Update `TOOL_BUILDERS` entry with new param. Regenerate baseline (`--force-regen -m kg`). |
| 9 | About content | `inputs/tools/list_organisms.yaml` | Add example: `list_organisms(organism_names=[...])`. Update mistakes list. Run `build_about_content.py`. |
| 10 | Docs | `CLAUDE.md` | Update tool-table entry for `list_organisms` to mention `organism_names` filter and `not_found`. |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_list_organisms` (updated)

```python
def build_list_organisms(
    *,
    organism_names_lc: list[str] | None = None,
    verbose: bool = False,
) -> tuple[str, dict]:
    """Build Cypher for listing organisms with data-availability signals.

    organism_names_lc: optional list of lowercased preferred_names.
        When None, returns all organisms. When non-None, restricts to
        organisms whose preferred_name (lowercased) is in the list.

    RETURN keys (compact): organism_name, organism_type, genus, species,
    strain, clade, ncbi_taxon_id, gene_count, publication_count,
    experiment_count, treatment_types, background_factors, omics_types,
    clustering_analysis_count, cluster_types, reference_database,
    reference_proteome, growth_phases.
    RETURN keys (verbose): adds family, order, tax_class, phylum, kingdom,
    superkingdom, lineage, cluster_count.
    """
```

**Cypher** (verified against live KG, see below):

```cypher
MATCH (o:OrganismTaxon)
WHERE $organism_names_lc IS NULL
   OR toLower(o.preferred_name) IN $organism_names_lc
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
       o.reference_database AS reference_database,
       o.reference_proteome AS reference_proteome,
       coalesce(o.growth_phases, []) AS growth_phases
       {verbose_columns}
ORDER BY o.genus, o.preferred_name
```

`{verbose_columns}` unchanged from today.

**Params:** `{"organism_names_lc": organism_names_lc}` always — Cypher
uses `IS NULL` to gate the filter so the parameter is always bound.

### `build_list_organisms_summary` (new)

Used to compute `total_entries` (unfiltered KG-wide count) without
running the full detail query when `summary=True` and a filter is set.

```python
def build_list_organisms_summary() -> tuple[str, dict]:
    """Build Cypher for KG-wide OrganismTaxon count.

    RETURN keys: total_entries.
    """
```

**Cypher:**

```cypher
MATCH (o:OrganismTaxon)
RETURN count(o) AS total_entries
```

### `not_found` lookup query (in api/, not a builder)

Mirrors `list_publications` pattern:

```cypher
MATCH (o:OrganismTaxon)
WHERE toLower(o.preferred_name) IN $names_lc
RETURN collect(toLower(o.preferred_name)) AS found
```

Used only when `organism_names` is provided. api/ takes the
case-insensitive set difference and returns inputs that didn't match,
preserving original casing.

### KG verification (verified 2026-04-26)

| Query | Expected | Actual | Pass |
|---|---|---|---|
| Filter by 2 known + 1 unknown name | 2 rows, both genome strains | `Prochlorococcus MED4`, `Prochlorococcus MIT9301` returned | ✓ |
| `collect(toLower(preferred_name))` for not_found | `["prochlorococcus med4", "prochlorococcus mit9301"]` | exact match | ✓ |
| `count(OrganismTaxon)` | 32 | 32 | ✓ |
| `WHERE null IS NULL OR toLower(...) IN null` short-circuit | all 32 returned | 32 | ✓ |
| `WHERE [...] IS NULL OR toLower(...) IN [...]` literal list | 1 row matching `'prochlorococcus med4'` | 1 row | ✓ |

---

## API Function

**File:** `api/functions.py`

```python
def list_organisms(
    organism_names: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List organisms in the knowledge graph, optionally filtered by name.

    organism_names: when provided, restricts results to organisms whose
        preferred_name matches (case-insensitive). Unknown names are
        returned in `not_found`.
    summary: when True, sets limit=0 internally — results=[], summary
        fields only.

    Returns dict with keys: total_entries, total_matching, returned,
    offset, truncated, by_cluster_type, by_organism_type, not_found,
    results.
    Per result and verbose-only fields: unchanged from prior behavior.
    """
```

**Logic outline:**

```python
conn = _default_conn(conn)
if summary:
    limit = 0

names_lc = [n.lower() for n in organism_names] if organism_names else None

cypher, params = build_list_organisms(
    organism_names_lc=names_lc, verbose=verbose,
)
matched = conn.execute_query(cypher, **params)
total_matching = len(matched)

# total_entries: KG-wide. Skip the extra query when no filter is set —
# total_matching == total_entries in that case.
if organism_names is None:
    total_entries = total_matching
else:
    summary_cypher, summary_params = build_list_organisms_summary()
    rows = conn.execute_query(summary_cypher, **summary_params)
    total_entries = rows[0]["total_entries"] if rows else 0

# Breakdowns over the matched set (unchanged loop logic).
ct_counts: dict[str, int] = {}
ot_counts: dict[str, int] = {}
for org in matched:
    for ct in org.get("cluster_types", []):
        ct_counts[ct] = ct_counts.get(ct, 0) + 1
    ot = org.get("organism_type")
    if ot:
        ot_counts[ot] = ot_counts.get(ot, 0) + 1

# Slice for limit/offset (limit=0 yields []).
if limit == 0:
    results = []
elif limit is None:
    results = matched[offset:]
else:
    results = matched[offset:offset + limit]

# Sparse-strip and verbose-gating: unchanged from today.

# not_found via separate query (only when filter provided).
if organism_names:
    not_found_cypher = (
        "MATCH (o:OrganismTaxon) "
        "WHERE toLower(o.preferred_name) IN $names_lc "
        "RETURN collect(toLower(o.preferred_name)) AS found"
    )
    rows = conn.execute_query(not_found_cypher, names_lc=names_lc)
    found = set(rows[0]["found"]) if rows else set()
    not_found = [n for n in organism_names if n.lower() not in found]
else:
    not_found = []

return {
    "total_entries": total_entries,
    "total_matching": total_matching,
    "by_cluster_type": _sorted_breakdown(ct_counts, "cluster_type"),
    "by_organism_type": _sorted_breakdown(ot_counts, "organism_type"),
    "returned": len(results),
    "offset": offset,
    "truncated": total_matching > offset + len(results),
    "not_found": not_found,
    "results": results,
}
```

**Notes:**
- 2-query pattern only when filter is set (one for `total_entries`, one
  for not_found). Skipped when no filter — saves 2 round-trips for the
  default unfiltered call.
- The existing `list_organisms` already builds breakdowns inline as
  sorted dict comprehensions. Keep that style — `_sorted_breakdown` is
  a local helper inside other api functions (e.g. `list_publications`),
  not a shared module-level utility, and we shouldn't promote it as
  part of this change.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

### Pydantic envelope (updated)

```python
class ListOrganismsResponse(BaseModel):
    total_entries: int = Field(description="Total organisms in the KG")
    total_matching: int = Field(description="Organisms matching the filter (= total_entries when no filter)")
    by_cluster_type: list[OrgClusterTypeBreakdown] = Field(
        default_factory=list,
        description="Organism counts per cluster type (over matched set), sorted by count descending",
    )
    by_organism_type: list[OrgTypeBreakdown] = Field(
        default_factory=list,
        description="Organism counts per type (over matched set), sorted by count descending",
    )
    returned: int = Field(description="Number of results returned")
    offset: int = Field(default=0, description="Offset into result set (e.g. 0)")
    truncated: bool = Field(description="True if total_matching > offset + returned")
    not_found: list[str] = Field(
        default_factory=list,
        description="organism_names inputs that didn't match any organism (case-insensitive); [] when no filter",
    )
    results: list[OrganismResult]
```

### Wrapper (updated)

```python
@mcp.tool(
    tags={"organisms", "discovery"},
    annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
async def list_organisms(
    ctx: Context,
    organism_names: Annotated[list[str] | None, Field(
        description=(
            "Filter by exact organism preferred_name (case-insensitive). "
            "Pass values from a prior list_organisms call or another "
            "tool's organism_name field. Unknown names are reported in "
            "not_found rather than raising."
        ),
    )] = None,
    summary: Annotated[bool, Field(
        description="Return summary fields only (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description=(
            "Include full taxonomy hierarchy (family, order, class, "
            "phylum, kingdom, superkingdom, lineage)."
        ),
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
    offset: Annotated[int, Field(
        description="Number of results to skip for pagination.", ge=0,
    )] = 0,
) -> ListOrganismsResponse:
    """List organisms in the knowledge graph, optionally filtered by name.

    Returns taxonomy, gene counts, publication counts, and organism_type
    for each organism. Use returned organism names as filter values in
    other tools.
    """
    await ctx.info(
        f"list_organisms organism_names={organism_names} "
        f"summary={summary} verbose={verbose} limit={limit} offset={offset}"
    )
    try:
        conn = _conn(ctx)
        result = api.list_organisms(
            organism_names=organism_names,
            summary=summary,
            verbose=verbose,
            limit=limit,
            offset=offset,
            conn=conn,
        )
        return ListOrganismsResponse(
            total_entries=result["total_entries"],
            total_matching=result["total_matching"],
            by_cluster_type=[OrgClusterTypeBreakdown(**b) for b in result.get("by_cluster_type", [])],
            by_organism_type=[OrgTypeBreakdown(**b) for b in result.get("by_organism_type", [])],
            returned=result["returned"],
            offset=result.get("offset", 0),
            truncated=result["truncated"],
            not_found=result.get("not_found", []),
            results=[OrganismResult(**r) for r in result["results"]],
        )
    except Exception as e:
        await ctx.error(f"list_organisms unexpected error: {e}")
        raise ToolError(f"Error in list_organisms: {e}")
```

---

## Tests

### Unit: query builder (extend `TestBuildListOrganisms`)

```
test_no_filter                — organism_names_lc=None → WHERE evaluates as null-OR
test_filter_in_clause         — organism_names_lc=[...] → IN clause present, param set
test_filter_param_passthrough — params dict carries organism_names_lc verbatim
test_summary_builder_returns_count_only — build_list_organisms_summary returns count(o)
```

### Unit: API function (extend `TestListOrganisms`)

```
test_passes_organism_names_lc      — api lowercases input list before forwarding
test_total_matching_no_filter      — total_matching == total_entries when filter None
test_total_matching_with_filter    — total_matching == len(matched), total_entries == 32
test_not_found_with_filter         — unknown names appear in not_found, original casing preserved
test_not_found_empty_when_no_filter
test_summary_flag_zeros_results    — summary=True → results=[], summary fields populated
test_breakdowns_over_filtered_set  — breakdown counts reflect matched rows only when filter set
test_truncation_uses_total_matching
```

### Unit: MCP wrapper (extend `TestListOrganismsWrapper`)

```
test_response_envelope_has_total_matching_and_not_found
test_organism_names_param_forwarded
test_summary_param_forwarded
test_filter_with_unknown_input_populates_not_found
```

`EXPECTED_TOOLS` already lists `list_organisms` — no change needed.

### Integration (`test_mcp_tools.py`)

Live-KG cases:
- `list_organisms(organism_names=["Prochlorococcus MED4", "Prochlorococcus MIT9301", "Bogus organism"])`
  → 2 results, `not_found == ["Bogus organism"]`, `total_matching == 2`, `total_entries == 32`.
- `list_organisms(summary=True)` → `results == []`, `total_matching == 32`, breakdowns populated.

### Regression (`test_regression.py`)

Update `TOOL_BUILDERS["list_organisms"]` so it forwards the new param.
Regenerate baselines:

```bash
pytest tests/regression/ --force-regen -m kg
```

### Eval cases (`tests/evals/cases.yaml`)

Add a case for the filter shape — both happy path and `not_found`.

---

## About Content

**File:** `multiomics_explorer/inputs/tools/list_organisms.yaml`

Add example:

```yaml
- title: Look up specific organisms
  call: list_organisms(organism_names=["Prochlorococcus MED4", "Prochlorococcus MIT9301"])
  response: |
    {"total_entries": 32, "total_matching": 2, "returned": 2, "truncated": false, "not_found": [], "results": [{"organism_name": "Prochlorococcus MED4", ...}, {"organism_name": "Prochlorococcus MIT9301", ...}]}
```

Add mistake notes:
- "organism_names matches preferred_name exactly (case-insensitive). Pass canonical names from a prior list_organisms call — short forms like 'MED4' will not match."
- "not_found contains inputs whose preferred_name didn't match any OrganismTaxon. It does not flag organisms that were filtered out by other constraints (there are none today, but this is the convention)."

Then regenerate:

```bash
uv run python scripts/build_about_content.py list_organisms
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Update `list_organisms` row: add "Filterable by `organism_names`. Returns `not_found` when `organism_names` includes unknown values." to mirror sibling-tool wording. |
