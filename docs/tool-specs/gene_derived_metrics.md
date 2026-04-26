# Tool spec: gene_derived_metrics

**Design spec:** [`docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md`](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md) — shared slice-1 contract (KG invariants, gate logic, envelope conventions, polymorphic-`value` rules). This file adds tool-specific verified Cypher and Pydantic surface.

## Purpose

Gene-centric batch lookup for `DerivedMetric` annotations — Tool 2 of slice 1, mirrors `gene_clusters_by_gene`. Answers "given these locus_tags, what derived-metric annotations does each gene carry across numeric / boolean / categorical kinds?" Single organism enforced (matches `gene_clusters_by_gene` and `gene_ontology_terms`). One row per gene × DM pair, with a polymorphic `value` column and CASE-gated sparse extras for numeric rankable / has_p_value DMs.

## Out of Scope

- **Discovery / per-paper inventory** — use `list_derived_metrics`.
- **Filter by numeric edge thresholds (`min_value`, `bucket`, `min_percentile`, etc.)** — pivot to `genes_by_numeric_metric`. This tool intentionally has no edge-level numeric filters; it is the gene-anchor surface.
- **Cross-organism queries** — single organism enforced; for cross-organism DM views, scope by ortholog group (slice 2) or call once per organism.
- **Member-gene drill-down for a DM** — use the three `genes_by_{kind}_metric` tools.

## Status / Prerequisites

- [x] KG changes landed (non-DE evidence extension — `multiomics_biocypher_kg/docs/kg-changes/non-de-evidence-extension.md`)
- [x] Scope reviewed with user (slice-1 design spec, 2026-04-23)
- [x] Result-size controls decided (batch tool — `summary` + `verbose` + `limit`; `not_found` + `not_matched` plumbing)
- [x] KG invariants verified live (2026-04-26 — KG has grown since slice spec was written; baselines refreshed below)
- [x] **KG cleanup landed (2026-04-26):** [docs/kg-specs/2026-04-26-unify-derived-metric-edge-value.md](../kg-specs/2026-04-26-unify-derived-metric-edge-value.md). All three DM edge types now expose `[id, metric_type, value]`; `value_flag` / `value_text` are gone. Verified live: 5,114 quantifies + 4,694 flags + 316 classifies edges all carry `r.value`; rankable extras intact (0 missing); boolean values still string `"true"` (BioCypher constraint, expected). Tool spec below uses the simplified Cypher (no `properties(r)` projection, no `CASE dm.value_kind` switch).
- [ ] Build plan approved (then Phase 2)

**Spec freeze.** Per the `add-or-update-tool` skill: once the user signs off, this spec is frozen — adding result fields, removing parameters, or changing the query architecture during build requires re-approval. Design iteration belongs in Phase 1.

## Use cases

- **Gene-centric triage.** "What non-DE evidence (rhythmicity flags, diel amplitudes, vesicle proteome membership, subcellular localization) does each of these genes carry?"
- **DE follow-up.** Given a hit list from `differential_expression_by_gene` or `genes_by_function`, annotate with DM signal in one batch call. The polymorphic-`value` row format makes this easy to pivot client-side.
- **Cross-tool chaining.** `differential_expression_by_gene` → `gene_derived_metrics` → `genes_by_numeric_metric(derived_metric_ids=…, bucket=[…])` to drill into ranking on selected DMs.
- **Quick filter to one kind.** `gene_derived_metrics(locus_tags=…, value_kind='boolean')` answers "which of these genes are in the vesicle proteome?" without round-tripping through `list_derived_metrics`.

## KG dependencies

Verified live 2026-04-26:

- `Gene` nodes — `locus_tag` (key), `gene_name`, `organism_name`. Per-kind rollup props (used for `genes_with_metrics` / `genes_without_metrics` in the summary, and as a fast-path):
  - `g.numeric_metric_count` (int, default 0), `g.numeric_metric_types_observed` (str[], default [])
  - `g.classifier_flag_count`, `g.classifier_flag_types_observed`
  - `g.classifier_label_count`, `g.classifier_label_types_observed`
  - `g.compartments_observed` (str[]) — set of compartments this gene's DMs span
  - Naming is per-kind, **not** unified. See slice spec §"KG invariants" §5.
- `DerivedMetric` nodes — fully denormalized parent fields (`organism_name`, `experiment_id`, `publication_doi`, `compartment`, `treatment_type`, `background_factors`, `growth_phases`, `omics_type`); `metric_type`, `value_kind`, `rankable`, `has_p_value`, `unit`, `allowed_categories`, `name`, `field_description`, plus verbose-only `treatment`, `light_condition`, `experimental_context`.
- Three edge types from `DerivedMetric` to `Gene`, all sharing `{id, metric_type, value}` after the 2026-04-26 edge-value unification rebuild:
  - `Derived_metric_quantifies_gene` — `r.value: float`; plus `{rank_by_metric, metric_percentile, metric_bucket}` only when parent `dm.rankable='true'`; plus `{adjusted_p_value, significant, p_value}` only when parent `dm.has_p_value='true'` (none today — see *Special handling*).
  - `Derived_metric_flags_gene` — `r.value: str` (`"true"` / `"false"`; BioCypher cannot emit Neo4j-native bools, so flag is string-typed).
  - `Derived_metric_classifies_gene` — `r.value: str` (category string; must be a member of parent `dm.allowed_categories`).
- String-typed booleans on DM nodes and boolean edges. Compare with `= 'true'` in Cypher; coerce to Python `bool` in RETURN with `dm.rankable = 'true' AS rankable` (mirrors `list_derived_metrics`).
- Boolean storage is positive-only today (only `r.value='true'` rows exist on flags edges); see slice spec §"KG invariants" §4. Filter behavior is downstream's concern (`genes_by_boolean_metric`); this tool returns whatever is materialized.

### Refreshed live-KG baselines (2026-04-26 — supersedes slice spec)

| Quantity | Slice spec (2026-04-23) | Today (2026-04-26) |
|---|---|---|
| Total `DerivedMetric` nodes | 13 | **34** |
| `value_kind` breakdown | 6 numeric / 6 boolean / 1 categorical | **15 numeric / 16 boolean / 3 categorical** |
| `Derived_metric_quantifies_gene` edges | 1,872 | **5,114** |
| `Derived_metric_flags_gene` edges | 4,160 | **4,694** |
| `Derived_metric_classifies_gene` edges | 258 | **316** |
| Distinct publication DOIs | 2 | **6** |
| `compartment` values present | `whole_cell` | `whole_cell`, `vesicle` |

New papers contributing DMs since the slice design: Biller 2014 (`science.1243457`, vesicle proteome — boolean + categorical + numeric on MED4 and MIT9313), Brandt 2024 (`1462-2920.15834`, MIT9312 vesicle abundance — numeric), Wienhausen 2017 (`ismej.2017.189`, EZ55 chemotaxis — boolean). KG integration test baselines below pin to today's counts.

## Tool Signature

```python
@mcp.tool(
    tags={"derived-metrics", "genes", "batch"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def gene_derived_metrics(
    ctx: Context,
    locus_tags: Annotated[list[str], Field(
        description="Gene locus tags to look up (e.g. ['PMM1714', 'PMM0001']). "
                    "Required, non-empty. Single organism enforced — locus_tags "
                    "must all resolve to the same organism (or pair with "
                    "`organism` to disambiguate).",
    )],
    organism: Annotated[str | None, Field(
        description="Organism to scope to. Accepts short strain code ('MED4', "
                    "'NATL2A', 'MIT1002') or full name. Case-insensitive "
                    "substring match. Inferred from locus_tags when omitted; "
                    "raises if locus_tags span more than one organism.",
    )] = None,
    metric_types: Annotated[list[str] | None, Field(
        description="Filter by metric_type tags (e.g. 'diel_amplitude_protein_log2', "
                    "'vesicle_proteome_member'). Same metric_type may appear across "
                    "publications — pair with publication_doi or use "
                    "derived_metric_ids to pin one specific DM.",
    )] = None,
    value_kind: Annotated[Literal["numeric", "boolean", "categorical"] | None, Field(
        description="Restrict to one DM kind. Each kind has a different `value` "
                    "column type — 'numeric' → float, 'boolean' → 'true'/'false', "
                    "'categorical' → category string. Sparse rank/percentile/bucket "
                    "extras are populated only on numeric rows from rankable DMs.",
    )] = None,
    compartment: Annotated[str | None, Field(
        description="Filter to DMs from one sample compartment "
                    "('whole_cell', 'vesicle', 'exoproteome', 'spent_medium', "
                    "'lysate'). Exact match.",
    )] = None,
    treatment_type: Annotated[list[str] | None, Field(
        description="Treatment type(s) to match. Returns DMs whose treatment_type "
                    "list overlaps ANY of the given values. Case-insensitive.",
    )] = None,
    background_factors: Annotated[list[str] | None, Field(
        description="Background experimental factor(s) to match. ANY-overlap. "
                    "Case-insensitive.",
    )] = None,
    publication_doi: Annotated[list[str] | None, Field(
        description="Filter by one or more publication DOIs. Exact match.",
    )] = None,
    derived_metric_ids: Annotated[list[str] | None, Field(
        description="Look up specific DMs by their unique id. Use to pin one DM "
                    "when the same metric_type appears across publications. Pair "
                    "with `list_derived_metrics` for discovery.",
    )] = None,
    summary: Annotated[bool, Field(
        description="Return summary fields only (counts, breakdowns, not_found / "
                    "not_matched). Sugar for limit=0; results=[].",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include detailed text fields per row: treatment, "
                    "light_condition, experimental_context, plus raw `p_value` "
                    "when the parent DM has_p_value=True.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max rows to return. Paginate with offset. Use "
                    "`summary=True` for summary-only (sets limit=0 internally).",
        ge=1,
    )] = 5,
    offset: Annotated[int, Field(
        description="Pagination offset (starting row, 0-indexed).", ge=0,
    )] = 0,
) -> GeneDerivedMetricsResponse:
    """Polymorphic `value` column — branch on `value_kind` per row; consult `list_derived_metrics(value_kind=…)` first to know which DMs exist and whether numeric rows carry rank/percentile/bucket extras (rankable gate) or `adjusted_p_value`/`significant` (has_p_value gate).

    Gene-centric batch lookup for DerivedMetric annotations — one row per
    gene × DM. `value` is `float` on numeric rows, `'true'`/`'false'` on
    boolean rows, category string on categorical rows. Numeric extras
    (`rank_by_metric`, `metric_percentile`, `metric_bucket`) are populated
    only when the parent DM is rankable; null otherwise. Same gate for
    `adjusted_p_value` / `significant` on has_p_value DMs (none in the
    current KG).

    Single organism enforced. `not_found` (locus_tag absent from KG) and
    `not_matched` (in KG but no DM rows after filters — includes
    kind-mismatch when `value_kind` is set) make empty rows diagnosable.
    For edge-level numeric filters (bucket / percentile / rank / value
    thresholds), pivot to `genes_by_numeric_metric`.
    """
```

## Result-size controls

Batch input pattern — `summary` + `verbose` + `limit`. Default `limit=5` (small enough for the LLM to see summary + a few example rows in one call without flooding context). Detail query is skipped when `limit==0`.

### Summary envelope

| Field | Type | Description |
|---|---|---|
| `total_matching` | int | Rows (gene × DM pairs) matching all filters. |
| `total_derived_metrics` | int | Distinct DMs touching any of the input genes after filters. |
| `genes_with_metrics` | int | Input genes with ≥1 matching DM row. |
| `genes_without_metrics` | int | Input genes that exist in KG but have 0 matching DM rows after filters (i.e. `len(found_tags) - genes_with_metrics`; equals `len(not_matched)`). |
| `not_found` | list[str] | Input `locus_tags` absent from the KG (echo). |
| `not_matched` | list[str] | Input `locus_tags` present in KG but with zero DM rows after filters. |
| `by_value_kind` | list[{value_kind, count}] | Rows per value_kind. |
| `by_metric_type` | list[{metric_type, count}] | Rows per metric_type — coarse rollup. Same metric_type may aggregate across publications (e.g. `vesicle_proteome_member` exists separately for MED4 and MIT9313). |
| `by_metric` | list[{derived_metric_id, name, metric_type, value_kind, count}] | Rows per unique DM — fine breakdown that disambiguates within a metric_type. Self-describing: embeds `name`, `metric_type`, `value_kind` so the LLM can pick a `derived_metric_id` for downstream `genes_by_{kind}_metric` drill-downs without round-tripping to `list_derived_metrics`. Sorted by count desc. Mirrors `genes_in_cluster.by_cluster` shape. |
| `by_compartment` | list[{compartment, count}] | Rows per compartment. |
| `by_treatment_type` | list[{treatment_type, count}] | Flattened ANY-overlap. |
| `by_background_factors` | list[{background_factor, count}] | Flattened. |
| `by_publication` | list[{publication_doi, count}] | Rows per parent paper. |
| `returned` | int | `len(results)`. |
| `offset` | int | Echo of input. |
| `truncated` | bool | `total_matching > offset + returned`. |

### Detail (per-row compact, 13 fields)

**Identity / routing (6):** `locus_tag`, `gene_name`, `derived_metric_id`, `value_kind`, `name`, `value`

**Gate echoes (2):** `rankable`, `has_p_value` — sourced from the parent DM, coerced to Python `bool`. Echoed on every row so the LLM can interpret null sparse extras (below) without re-querying `list_derived_metrics`.

**Sparse numeric extras (5 in Pydantic; 3 in current Cypher RETURN):** null on boolean / categorical rows; doubly sparse on numeric rows per *KG invariants*.

- *Populated when parent `rankable='true'`:* `rank_by_metric`, `metric_percentile`, `metric_bucket` — emitted today.
- *Populated when parent `has_p_value='true'`:* `adjusted_p_value`, `significant` — **declared in Pydantic with `default=None` (forward-compat row shape); intentionally absent from the current Cypher RETURN** because no edge in the KG carries those props today and including them produces CyVer schema warnings (`The label Derived_metric_quantifies_gene does not have the following properties: adjusted_p_value, significant`). Mirrors the `p_value_threshold` deferral rule in [`list_derived_metrics.md`](list_derived_metrics.md). Re-add the CASE-gated RETURN columns (`CASE WHEN dm.has_p_value = 'true' THEN r.adjusted_p_value ELSE null END AS adjusted_p_value`, same for `significant`) when a `has_p_value='true'` DM lands.

**Diverges from slice spec.** The slice-1 design spec listed 16 compact fields plus the 5 sparse extras. Phase-1 trim moves 8 fields to verbose (per "Verbose adds" below): the row was too wide for batch responses, and the rolled-up envelope fields (`by_metric_type`, `by_compartment`, `by_treatment_type`, `by_background_factors`, `by_publication`) plus `derived_metric_id` (unique-key) + `name` (human label) + `value_kind` (routing) carry the routing-essential info already. The same trim likely applies to slice-1 tools 3–5 (`genes_by_{kind}_metric`) — flag during their phase-1 specs.

### Verbose adds (12 fields)

Moved from compact (8): `metric_type`, `field_description`, `unit`, `allowed_categories`, `compartment`, `treatment_type`, `background_factors`, `publication_doi`.

Heavy text / experiment context (3): `treatment`, `light_condition`, `experimental_context` (always; sourced from `dm.*`).

Sparse / forward-compat (1): `p_value` (raw, edge-side) — *populated only when parent `has_p_value='true'`*. Pydantic field stays declared; current Cypher RETURN omits the gated edge column to avoid CyVer schema warnings (no edge in the KG carries the property today). Re-enable when a `has_p_value='true'` DM lands; see *Special handling* below.

### `value` polymorphism

After the 2026-04-26 edge-value unification rebuild, all three edge types expose the measurement under `r.value` — single column, no `properties(r)` projection, no `CASE dm.value_kind` switch in RETURN. The column is heterogeneously typed across rows:

- `float` — numeric rows
- `"true"` / `"false"` string — boolean rows; matches edge storage so callers compare against the same vocabulary used by `genes_by_boolean_metric`'s `flag` filter
- category string — categorical rows; member of parent `dm.allowed_categories`

Pydantic typing: `value: float | str` (Pydantic accepts either). Documented in the YAML `mistakes` block (per slice spec §"Required `mistakes` + `chaining` coverage").

### Sort key

`g.locus_tag ASC, dm.value_kind ASC, dm.id ASC` — gene-anchored grouping, then kind (so a gene's numeric / boolean / categorical rows are blocked together for human reading), then DM id as deterministic tie-breaker for stable pagination.

## Special handling

- **`compartment` filter is exact-match.** `compartment` is a controlled vocabulary on `DerivedMetric` (5 known values: `whole_cell`, `vesicle`, `exoproteome`, `spent_medium`, `lysate`; only `whole_cell` and `vesicle` populated today). Mirroring `list_derived_metrics`, the filter is `dm.compartment = $compartment` rather than the case-insensitive CONTAINS / `toLower` pattern used for free-text fields like `organism_name`. The wrapper signature uses `Annotated[str | None, Field(...)]` (matching `list_derived_metrics`); kept as `str` rather than `Literal[...]` so the surface stays open as new compartments land — the controlled vocabulary lives in the Field description and `list_filter_values` rather than in the type annotation.
- **Polymorphic `value` is direct `r.value`.** After the 2026-04-26 KG rebuild, all 3 DM edge types expose the measurement under `r.value` (float on quantifies, string `"true"`/`"false"` on flags, category string on classifies). Single `r.value AS value` in RETURN — no map projection, no `CASE dm.value_kind` switch, no schema warnings. Consumers branch on `value_kind` to type-interpret each row.
- **Defensive CASE-gating.** Per slice spec canonical pattern, every gate-dependent column wraps in `CASE WHEN dm.rankable = 'true' THEN r.<col> ELSE null END` (and `dm.has_p_value = 'true'` for the p-value family). DM-level flag is the source of truth, not edge presence — robust to KG build bugs (e.g. a future DM accidentally getting `rankable='false'` set but edges still carrying `rank_by_metric`).
- **Single-organism enforcement.** Use existing `_validate_organism_inputs(organism, locus_tags, experiment_ids=None, conn)` helper — same pattern as `gene_clusters_by_gene` and `gene_ontology_terms`. Raises `ValueError` on cross-organism locus_tag input or organism-arg mismatch.
- **Empty `locus_tags`.** `ValueError("locus_tags must not be empty.")` at api/ entry — matches existing batch tools.
- **`summary=True` shortcut.** Force `limit=0`; detail query skipped; `results=[]`.
- **Forward-compat for `p_value`.** Verbose adds the row mapping in the Pydantic model only; the Cypher RETURN omits the edge `p_value` column today. When a DM with `has_p_value='true'` lands, add `CASE WHEN dm.has_p_value = 'true' THEN r.p_value ELSE null END AS p_value` to the verbose RETURN block (mirrors the `p_value_threshold` rule in `list_derived_metrics.md`).
- **Sparse-column shape stability.** Both numeric extras blocks (`rank_*` / `metric_*` and `adjusted_p_value` / `significant`) are *always present* in every row dict — null when the gate is off. This keeps the row shape uniform across `value_kind`s; consumers can flatten to a DataFrame without column-realignment surprises. Boolean and categorical rows just get null in those columns.

---

## Query Builder

**File:** `multiomics_explorer/kg/queries_lib.py`

Two builders, no shared WHERE helper (the WHERE expressions on `dm` are short and only used twice — extracting a helper adds indirection without saving lines, unlike the `_list_derived_metrics_where` case which is shared across summary + detail in `list_derived_metrics`).

### `build_gene_derived_metrics_summary`

Verified against live KG 2026-04-26 with `locus_tags=['PMN2A_2128', 'PMM1714', 'PMM_FAKE']` (a NATL2A gene with boolean-only DM signal, an MED4 gene with all 3 kinds, and a fake locus_tag).

| Filter | total_matching | total_derived_metrics | genes_with_metrics | genes_without_metrics | not_found | not_matched | by_value_kind |
|---|---|---|---|---|---|---|---|
| (none) | **12** | 12 | 2 | 0 | `['PMM_FAKE']` | `[]` | numeric=7, boolean=4, categorical=1 |
| `value_kind='numeric'` | **7** | 7 | 1 | 1 | `['PMM_FAKE']` | `['PMN2A_2128']` | numeric=7 |

Summary↔detail consistency check: detail builder over the same input (no filter) returns 12 rows = `total_matching` ✓. The kind-mismatch path is correctly bucketed: `PMN2A_2128` (boolean-only) lands in `not_matched` when filtering to numeric, rather than being silently swallowed.

`by_metric` verified for the no-filter case: 12 entries, each with `count=1` (each DM is touched by exactly one of the two found genes), every entry self-describing with `derived_metric_id` / `name` / `metric_type` / `value_kind` / `count`.

```cypher
UNWIND $locus_tags AS lt
OPTIONAL MATCH (g:Gene {locus_tag: lt})
OPTIONAL MATCH (g)<-[r:Derived_metric_quantifies_gene
                    |Derived_metric_flags_gene
                    |Derived_metric_classifies_gene]-(dm:DerivedMetric)
WHERE dm IS NULL OR ( <dm-level conditions from filter args> )
WITH lt, g, dm, $locus_tags AS input_tags
WITH input_tags,
     collect(DISTINCT CASE WHEN g IS NULL THEN lt END) AS nf_raw,
     collect(DISTINCT CASE WHEN g IS NOT NULL AND dm IS NULL THEN lt END) AS nm_raw,
     collect(CASE WHEN dm IS NOT NULL THEN
       {lt: lt, dm_id: dm.id, name: dm.name,
        mt: dm.metric_type, vk: dm.value_kind,
        comp: dm.compartment, doi: dm.publication_doi,
        tt: dm.treatment_type, bfs: dm.background_factors} END) AS rows
WITH input_tags,
     [x IN nf_raw WHERE x IS NOT NULL] AS not_found,
     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched,
     rows
RETURN size(rows) AS total_matching,
       size(apoc.coll.toSet([r IN rows | r.dm_id])) AS total_derived_metrics,
       size(apoc.coll.toSet([r IN rows | r.lt])) AS genes_with_metrics,
       size(input_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))
         - size(not_found) AS genes_without_metrics,
       not_found, not_matched,
       apoc.coll.frequencies([r IN rows | r.vk]) AS by_value_kind,
       apoc.coll.frequencies([r IN rows | r.mt]) AS by_metric_type,
       [dm_id IN apoc.coll.toSet([r IN rows | r.dm_id]) |
         {derived_metric_id: dm_id,
          name: head([r IN rows WHERE r.dm_id = dm_id | r.name]),
          metric_type: head([r IN rows WHERE r.dm_id = dm_id | r.mt]),
          value_kind: head([r IN rows WHERE r.dm_id = dm_id | r.vk]),
          count: size([r IN rows WHERE r.dm_id = dm_id])}] AS by_metric,
       apoc.coll.frequencies([r IN rows | r.comp]) AS by_compartment,
       apoc.coll.frequencies(
         apoc.coll.flatten([r IN rows | coalesce(r.tt, [])])) AS by_treatment_type,
       apoc.coll.frequencies(
         apoc.coll.flatten([r IN rows | coalesce(r.bfs, [])])) AS by_background_factors,
       apoc.coll.frequencies([r IN rows | r.doi]) AS by_publication
```

WHERE conditions on `dm` (all wrapped inside `dm IS NULL OR ( ... )` so the OPTIONAL MATCH still emits a "no edge" row for not_matched bookkeeping):

```
metric_types        → dm.metric_type IN $metric_types
value_kind          → dm.value_kind = $value_kind
compartment         → dm.compartment = $compartment
treatment_type      → ANY(t IN coalesce(dm.treatment_type, [])
                           WHERE toLower(t) IN $treatment_types_lower)
background_factors  → ANY(bf IN coalesce(dm.background_factors, [])
                           WHERE toLower(bf) IN $bfs_lower)
publication_doi     → dm.publication_doi IN $publication_doi
derived_metric_ids  → dm.id IN $derived_metric_ids
```

When *no* DM-level filters are passed, the entire `WHERE dm IS NULL OR (…)` clause is omitted (OPTIONAL MATCH alone is correct).

`organism` is enforced upstream (`_validate_organism_inputs`), not as a Cypher condition — same as `gene_clusters_by_gene`.

**CyVer warnings on map-literal keys.** Map keys like `{lt: lt, dm_id: dm.id, …}` trigger benign "missing property name" warnings (CyVer cross-references map keys against KG property names). The cluster summary builder already accepts identical warnings (see `build_gene_clusters_by_gene_summary` map literal `{lt, cid, ct, tt, bfs, aid, aname}`); we follow the existing convention.

### `build_gene_derived_metrics`

Verified against live KG 2026-04-26 (post edge-value unification rebuild) with `locus_tags=['PMM1714']` → 9 rows; `r.value` returns float / `'true'` / `'Cytoplasmic Membrane'` directly with zero CyVer schema warnings; sparse rank/percentile/bucket null on non-rankable rows.

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})
MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene
                          |Derived_metric_flags_gene
                          |Derived_metric_classifies_gene]->(g)
<WHERE-block from filter args, AND-joined>
RETURN g.locus_tag AS locus_tag,
       g.gene_name AS gene_name,
       dm.id AS derived_metric_id,
       dm.value_kind AS value_kind,
       dm.name AS name,
       r.value AS value,
       dm.rankable = 'true' AS rankable,
       dm.has_p_value = 'true' AS has_p_value,
       CASE WHEN dm.rankable = 'true' THEN r.rank_by_metric ELSE null END AS rank_by_metric,
       CASE WHEN dm.rankable = 'true' THEN r.metric_percentile ELSE null END AS metric_percentile,
       CASE WHEN dm.rankable = 'true' THEN r.metric_bucket ELSE null END AS metric_bucket
       -- adjusted_p_value, significant: declared in Pydantic Result model
       --   (default=None) but NOT in the current Cypher RETURN — no edge
       --   carries those props today and including them generates CyVer
       --   warnings. Re-add when a has_p_value='true' DM lands.
       <verbose cols when verbose=True>
ORDER BY g.locus_tag ASC, dm.value_kind ASC, dm.id ASC
SKIP $offset
LIMIT $limit
```

WHERE block: same DM-level conditions as the summary, AND-joined. (No `dm IS NULL OR …` wrapping here — the detail query uses plain `MATCH`, so non-matching rows simply don't appear; `not_found` / `not_matched` are tracked entirely by the summary.)

Verbose RETURN additions (12 fields):

```
,
       dm.metric_type AS metric_type,
       dm.field_description AS field_description,
       dm.unit AS unit,
       CASE WHEN dm.value_kind = 'categorical'
            THEN dm.allowed_categories ELSE null END AS allowed_categories,
       dm.compartment AS compartment,
       coalesce(dm.treatment_type, []) AS treatment_type,
       coalesce(dm.background_factors, []) AS background_factors,
       dm.publication_doi AS publication_doi,
       dm.treatment AS treatment,
       dm.light_condition AS light_condition,
       dm.experimental_context AS experimental_context
```

`p_value` (edge-side) is intentionally absent until a `has_p_value='true'` DM lands (see *Special handling*).

**Variable scoping.** Single MATCH chain, RETURN reads directly from `r.<key>` and `dm.<key>`. No `WITH g, dm, r, properties(r) AS p` projection (the rebuild made the map-projection workaround unnecessary). No UNWIND of intermediate collects. SKIP/LIMIT on a deterministic ORDER BY means pagination is stable across calls.

**Why no DISTINCT?** Each `(dm, r, g)` triple is unique by construction (one edge per DM × Gene), so deduplication is unnecessary. Cluster builders skip DISTINCT for the same reason.

---

## API Function

**File:** `multiomics_explorer/api/functions.py`

```python
def gene_derived_metrics(
    locus_tags: list[str],
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean", "categorical"] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Gene-centric DerivedMetric lookup. Single organism enforced.

    Returns dict with keys: total_matching, total_derived_metrics,
    genes_with_metrics, genes_without_metrics, not_found, not_matched,
    by_value_kind, by_metric_type, by_metric, by_compartment,
    by_treatment_type, by_background_factors, by_publication,
    returned, offset, truncated, results.
    Per result (compact, 13 fields): locus_tag, gene_name,
    derived_metric_id, value_kind, name, value, rankable, has_p_value,
    rank_by_metric, metric_percentile, metric_bucket,
    adjusted_p_value, significant.
    Per result (verbose adds): metric_type, field_description, unit,
    allowed_categories, compartment, treatment_type, background_factors,
    publication_doi, treatment, light_condition, experimental_context,
    p_value.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: locus_tags empty, or spans multiple organisms,
                    or organism arg conflicts with inferred organism.
    """
```

Implementation notes:

- `if not locus_tags: raise ValueError(...)` — matches existing batch tools.
- `if summary: limit = 0`.
- `_validate_organism_inputs(organism=organism, locus_tags=locus_tags, experiment_ids=None, conn=conn)` — single-organism gate, raises on conflict. (Same call shape as `gene_clusters_by_gene`.)
- 2-query pattern: summary always runs (provides `not_found` / `not_matched` plumbing); detail skipped when `limit==0`.
- Envelope assembly: `_rename_freq` on each `apoc.coll.frequencies` block (mirrors `gene_clusters_by_gene`):
  - `by_value_kind` → `value_kind`
  - `by_metric_type` → `metric_type`
  - `by_compartment` → `compartment`
  - `by_treatment_type` → `treatment_type`
  - `by_background_factors` → `background_factor`
  - `by_publication` → `publication_doi`
- `by_metric` is **already shaped** by the summary builder (per-DM dicts with `derived_metric_id`/`name`/`metric_type`/`value_kind`/`count`) — no `_rename_freq` call. Sort by `count` descending in the api/ layer (Cypher returns set-iteration order, which is non-deterministic).
- `truncated = total_matching > offset + len(results)` — same convention.
- Wire exports: add to `api/__init__.py` and `multiomics_explorer/__init__.py` `__all__`.

---

## MCP Wrapper

**File:** `multiomics_explorer/mcp_server/tools.py`

Two Pydantic models: `GeneDerivedMetricsResult` (one row) and `GeneDerivedMetricsResponse` (envelope), inside `register_tools(mcp)`. Seven small per-dimension breakdown models (`*Breakdown`) at module top, mirroring the cluster pattern (`GeneClusterTypeBreakdown`, etc.). The `GeneDmMetricBreakdown` model is wider than the other six (5 fields vs 2) — matches the `genes_in_cluster` `by_cluster` shape.

```python
class GeneDmMetricBreakdown(BaseModel):
    derived_metric_id: str = Field(description="Unique DM id.")
    name: str = Field(description="Human-readable DM name.")
    metric_type: str = Field(description="Category tag.")
    value_kind: Literal["numeric", "boolean", "categorical"] = Field(
        description="Routes to the matching genes_by_*_metric drill-down.")
    count: int = Field(description="Rows contributed by this DM.")
```

The other six follow the standard `{<key>, count}` shape:
`GeneDmValueKindBreakdown` (`value_kind`), `GeneDmMetricTypeBreakdown` (`metric_type`), `GeneDmCompartmentBreakdown` (`compartment`), `GeneDmTreatmentBreakdown` (`treatment_type`), `GeneDmBackgroundFactorBreakdown` (`background_factor`), `GeneDmPublicationBreakdown` (`publication_doi`).

```python
class GeneDerivedMetricsResult(BaseModel):
    # ── compact (always populated) ──────────────────────────────────
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM1714').")
    gene_name: str | None = Field(default=None,
        description="Gene name (e.g. 'dnaN') — null when the KG has no name.")
    derived_metric_id: str = Field(
        description="Unique parent-DM id. Pass to `derived_metric_ids` on "
                    "genes_by_*_metric drill-downs to pin this exact DM. "
                    "metric_type, compartment, publication_doi etc. are "
                    "available on this row in verbose mode, or via "
                    "`list_derived_metrics(derived_metric_ids=[...])`.")
    value_kind: Literal["numeric", "boolean", "categorical"] = Field(
        description="Determines how to interpret `value`. Routes to the "
                    "matching genes_by_*_metric drill-down.")
    name: str = Field(
        description="Human-readable DM name (e.g. 'Transcript:protein "
                    "amplitude ratio'). Saves a round-trip to "
                    "list_derived_metrics for opaque metric_type codes.")
    value: float | str = Field(
        description="Polymorphic measurement: float on numeric rows, 'true'/"
                    "'false' string on boolean rows, category string on "
                    "categorical rows. Branch on `value_kind` to interpret.")
    rankable: bool = Field(
        description="Echoed from parent DM. True iff this row's `value` "
                    "carries rank/percentile/bucket extras (numeric rows "
                    "only); null in those extra columns when False.")
    has_p_value: bool = Field(
        description="Echoed from parent DM. True iff `adjusted_p_value` / "
                    "`significant` (and verbose `p_value`) carry data; null "
                    "otherwise. No DM in the current KG has p-values.")
    rank_by_metric: int | None = Field(default=None,
        description="Rank of this gene by metric value (1 = highest). "
                    "Populated only when parent DM rankable=True; null on "
                    "boolean / categorical / non-rankable numeric rows.")
    metric_percentile: float | None = Field(default=None,
        description="Percentile within metric distribution (0–100). Same "
                    "gate as rank_by_metric.")
    metric_bucket: str | None = Field(default=None,
        description="Bucket label ('top_decile', 'top_quartile', 'mid', "
                    "'low'). Same gate as rank_by_metric.")
    adjusted_p_value: float | None = Field(default=None,
        description="BH-adjusted p-value. Populated only when parent DM "
                    "has_p_value=True. No DM in the current KG carries "
                    "p-values; column kept compact for forward-compat row "
                    "shape stability.")
    significant: bool | None = Field(default=None,
        description="Significance flag at the DM's p_value_threshold. Same "
                    "gate as adjusted_p_value.")
    # ── verbose adds (default None / [] when verbose=False) ─────────
    metric_type: str | None = Field(default=None,
        description="Category tag for this DM (e.g. 'damping_ratio'). Same "
                    "metric_type may appear across publications — use "
                    "derived_metric_id to pin one. Verbose only.")
    field_description: str | None = Field(default=None,
        description="Detailed explanation of what this DM measures. "
                    "Verbose only.")
    unit: str | None = Field(default=None,
        description="Measurement unit for numeric DMs (e.g. 'hours', 'log2'). "
                    "Empty string for boolean / categorical rows. Verbose only.")
    allowed_categories: list[str] | None = Field(default=None,
        description="Valid category strings — non-null only on categorical "
                    "rows. Verbose only.")
    compartment: str | None = Field(default=None,
        description="Sample compartment ('whole_cell', 'vesicle', "
                    "'exoproteome', 'spent_medium', 'lysate'). Verbose only.")
    treatment_type: list[str] = Field(default_factory=list,
        description="Treatment type(s) for the parent experiment. Verbose only.")
    background_factors: list[str] = Field(default_factory=list,
        description="Background experimental factors (may be empty). "
                    "Verbose only.")
    publication_doi: str | None = Field(default=None,
        description="Parent publication DOI. Verbose only.")
    treatment: str | None = Field(default=None,
        description="Treatment description in plain language. Verbose only.")
    light_condition: str | None = Field(default=None,
        description="Light regime. Verbose only.")
    experimental_context: str | None = Field(default=None,
        description="Longer experimental setup description. Verbose only.")
    p_value: float | None = Field(default=None,
        description="Raw p-value. Populated only when parent DM "
                    "has_p_value=True (none in current KG). Verbose only.")


class GeneDerivedMetricsResponse(BaseModel):
    total_matching: int = Field(
        description="Gene × DM rows matching all filters.")
    total_derived_metrics: int = Field(
        description="Distinct DMs touching the input genes after filters.")
    genes_with_metrics: int = Field(
        description="Input genes with ≥1 matching DM row.")
    genes_without_metrics: int = Field(
        description="Input genes present in KG but with zero matching DM rows.")
    not_found: list[str] = Field(default_factory=list,
        description="Input locus_tags absent from the KG (echo).")
    not_matched: list[str] = Field(default_factory=list,
        description="Input locus_tags in KG but with zero DM rows after filters.")
    by_value_kind: list["GeneDmValueKindBreakdown"] = Field(
        description="Rows per value_kind.")
    by_metric_type: list["GeneDmMetricTypeBreakdown"] = Field(
        description="Rows per metric_type — coarse rollup; same metric_type "
                    "may aggregate across publications.")
    by_metric: list["GeneDmMetricBreakdown"] = Field(
        description="Rows per unique DerivedMetric — fine breakdown that "
                    "disambiguates within a metric_type. Each entry embeds "
                    "name, metric_type, and value_kind so derived_metric_ids "
                    "can be picked for downstream drill-down without a "
                    "round-trip to list_derived_metrics. Sorted by count desc.")
    by_compartment: list["GeneDmCompartmentBreakdown"] = Field(
        description="Rows per compartment.")
    by_treatment_type: list["GeneDmTreatmentBreakdown"] = Field(
        description="Rows per treatment_type (flattened).")
    by_background_factors: list["GeneDmBackgroundFactorBreakdown"] = Field(
        description="Rows per background factor (flattened).")
    by_publication: list["GeneDmPublicationBreakdown"] = Field(
        description="Rows per parent publication.")
    returned: int = Field(description="Length of results list.")
    offset: int = Field(default=0, description="Pagination offset used.")
    truncated: bool = Field(
        description="True when total_matching > offset + returned.")
    results: list["GeneDerivedMetricsResult"] = Field(default_factory=list,
        description="One row per gene × DM. Empty when summary=True.")
```

Wrapper body: `await ctx.info(...)`, call `api.gene_derived_metrics`, build each breakdown list (and the `results` list) into **new local variables** — do not mutate the api/ return dict, since it may be a shared reference under test mocking (see `add-or-update-tool` checklist gotcha). Construct `GeneDerivedMetricsResponse(...)` with explicit kwargs (cluster wrapper pattern). `ToolError` on `ValueError`. ctx.info / ctx.warning / ctx.error messages mirror `gene_clusters_by_gene` style.

---

## Tests

### Unit: `tests/unit/test_query_builders.py::TestBuildGeneDerivedMetrics` + `TestBuildGeneDerivedMetricsSummary`

Detail builder:

- `test_no_filters` — bare unified-edge MATCH, no WHERE block, no SKIP/LIMIT params when limit=None.
- `test_metric_types_list` — `dm.metric_type IN $metric_types` + param.
- `test_value_kind` — `dm.value_kind = $value_kind`.
- `test_compartment`, `test_publication_doi_list`, `test_derived_metric_ids_list`.
- `test_treatment_type_lower`, `test_background_factors_lower` — case-insensitive ANY-overlap pattern; param keys lowercased.
- `test_combined_filters` — AND-joined, stable ordering.
- `test_returns_expected_compact_columns` — exactly **11** compact RETURN columns (the 13 Pydantic compact fields minus `adjusted_p_value` and `significant`, which are deferred from Cypher today; see *Detail (per-row compact)* §"Sparse numeric extras"). Asserts the 8 newly-verbose-only fields are *absent* from the compact RETURN.
- `test_value_is_direct_r_access` — RETURN contains `r.value AS value` (single column, no `CASE dm.value_kind` switch and no `properties(r)` projection — both removed after the 2026-04-26 KG edge-value unification).
- `test_rankable_case_gates` — RETURN wraps `rank_by_metric`, `metric_percentile`, `metric_bucket` in `CASE WHEN dm.rankable = 'true' …`.
- `test_has_p_value_columns_deferred` — RETURN does **not** contain `adjusted_p_value` / `significant` today (intentional, until a `has_p_value='true'` DM lands; mirrors `list_derived_metrics.test_p_value_threshold_deferred`).
- `test_verbose_adds_columns` — verbose path appends the **11** verbose RETURN fields emitted today (out of 12 Pydantic verbose fields; `p_value` is deferred along with the `has_p_value` family). Specifically asserts `metric_type`, `compartment`, `treatment_type`, `background_factors`, `publication_doi`, `field_description`, `unit`, `allowed_categories`, `treatment`, `light_condition`, `experimental_context` all appear in the verbose RETURN.
- `test_allowed_categories_case_gated_in_verbose` — verbose RETURN's `allowed_categories` is CASE-gated on `dm.value_kind = 'categorical'`.
- `test_p_value_deferred_in_verbose` — verbose RETURN does **not** contain `r.p_value` today (forward-compat; mirrors `has_p_value` deferral in compact).
- `test_rankable_has_p_value_coerced` — RETURN includes `dm.rankable = 'true' AS rankable` (Python bool coercion).
- `test_limit_offset` — SKIP / LIMIT clauses + params populated only when set.
- `test_order_by` — `g.locus_tag, dm.value_kind, dm.id`.

Summary builder (mirrors detail; covers the OPTIONAL MATCH cascade):

- `test_optional_match_cascade` — WHERE wraps `dm IS NULL OR (…)`; absent when no DM-level filters.
- `test_not_found_not_matched_collect` — emitted CASE expressions for `nf_raw` / `nm_raw`.
- `test_genes_without_metrics_arithmetic` — `size(input_tags) - size(... matched ...) - size(not_found)` expression present.
- `test_apoc_frequencies_blocks` — 5 frequency-style breakdowns + 1 self-shaped `by_metric` breakdown in RETURN (6 total breakdowns).
- `test_by_metric_shape` — `by_metric` projection in summary RETURN: per-DM dict with `derived_metric_id`, `name`, `metric_type`, `value_kind`, `count`. Asserts `name: dm.name` is included in the `rows` map literal.
- `test_total_derived_metrics` — `size(apoc.coll.toSet([r IN rows | r.dm_id]))`.
- `test_locus_tags_param` — `$locus_tags` in params.

### Unit: `tests/unit/test_api_functions.py::TestGeneDerivedMetrics`

Mocked `GraphConnection`. Cover:

- envelope shape (16 envelope keys + results),
- `summary=True` → `limit=0`, detail query NOT called, `results==[]`,
- `truncated` arithmetic (3 cases: full set returned, partial, empty),
- `not_found` plumbing (mocked summary returns it; api echoes),
- `not_matched` plumbing (kind-mismatch case: gene has only boolean DMs, value_kind='numeric' → not_matched),
- `genes_with_metrics` / `genes_without_metrics` consistency (`+ len(not_found) + len(not_matched) == len(input)`),
- `_validate_organism_inputs` integration (organism conflict raises),
- empty `locus_tags` raises `ValueError`,
- `_rename_freq` applied to the 5 frequency-style breakdowns (key naming),
- `by_metric` is **not** passed through `_rename_freq` (already has explicit keys); api/ sorts it by `count` descending.

### Unit: `tests/unit/test_tool_wrappers.py::TestGeneDerivedMetricsWrapper`

- update `EXPECTED_TOOLS`,
- `test_returns_response_envelope`,
- `test_polymorphic_value_field` — Pydantic `value: float | str` accepts both,
- `test_sparse_extras_default_none` — Result accepts row dicts with the 5 sparse extras absent (Pydantic `default=None`),
- `test_summary_empty_results`,
- `test_value_error_to_tool_error`.

### Integration (KG, `@pytest.mark.kg`): `tests/integration/test_mcp_tools.py::TestGeneDerivedMetrics`

Baselines pinned to 2026-04-26 KG state; refresh when new DM papers land.

- `test_pmm1714_all_three_kinds` — `gene_derived_metrics(['PMM1714'])` → 9 rows (7 numeric, 1 boolean, 1 categorical); `genes_with_metrics=1`; `total_derived_metrics=9`. Asserts polymorphic `value` types: floats on numeric rows, `'true'` on boolean, `'Cytoplasmic Membrane'` on categorical.
- `test_pmm0001_diel_only` — `gene_derived_metrics(['PMM0001'])` → 6 numeric Waldbauer rows; sparse rank/percentile/bucket null for `peak_time_*_h`, populated for the other 4.
- `test_value_kind_filter_routes_correctly` — `gene_derived_metrics(['PMM1714'], value_kind='boolean')` → 1 row (`vesicle_proteome_member`).
- `test_kind_mismatch_not_matched` — `gene_derived_metrics(['PMN2A_2128'], value_kind='numeric')` → 0 rows; `not_matched == ['PMN2A_2128']`; `genes_without_metrics == 1`. (NATL2A gene has only boolean DM signal.)
- `test_not_found_path` — `gene_derived_metrics(['PMM_DOES_NOT_EXIST'])` → 0 rows; `not_found == ['PMM_DOES_NOT_EXIST']`; `genes_without_metrics == 0`.
- `test_mixed_input` — `['PMM1714', 'PMM_FAKE', 'PMN2A_2128']` with `value_kind='numeric'` → forces all three diagnostic buckets to fire: `matched=['PMM1714']` (7 numeric rows), `not_found=['PMM_FAKE']`, `not_matched=['PMN2A_2128']` (boolean-only — kind-mismatch). `total_matching == 7`, `genes_with_metrics == 1`, `genes_without_metrics == 1`. Without the filter, PMN2A_2128's 3 boolean rows would land in `matched` and `not_matched` would be empty.
- `test_compartment_filter` — `compartment='vesicle'` against PMM1714 → 3 rows (the Biller 2014 boolean + categorical + numeric). Asserts compartment routing.
- `test_publication_doi_filter` — `publication_doi=['10.1371/journal.pone.0043432']` against PMM1714 → 6 Waldbauer numeric rows.
- `test_summary_only` — `summary=True` → `results==[]`; all `by_*` keys present (empty list when no rows, never missing).
- `test_by_metric_disambiguates` — `gene_derived_metrics(['PMM1714'], summary=True)` returns 9 entries in `by_metric` (one per DM touching the gene); each carries `name`, `metric_type`, `value_kind` for self-described drill-down. Compare against `by_metric_type`: same DMs collapse to fewer rows when metric_types repeat across publications (none today for PMM1714, so equal — keep the test as a structural assertion, not a count comparison).
- `test_verbose_columns` — verbose=True adds `treatment`, `light_condition`, `experimental_context`; `p_value` field is `None` (no DM with `has_p_value=true`).
- `test_organism_conflict_raises` — locus_tags from MED4 + NATL2A in one call → `ValueError`.
- `test_truncation` — `limit=2` against PMM1714 (9 total rows) → `returned==2`, `truncated==True`, `total_matching==9`.

### Contract: `tests/integration/test_api_contract.py::TestGeneDerivedMetricsContract`

Per `add-or-update-tool` checklist: api/ return shape changes need a contract test. Pin all 12 envelope keys + the union of compact/verbose result keys; fails fast on accidental shape drift.

### Correctness: `tests/integration/test_tool_correctness_kg.py`

Add `TestBuildGeneDerivedMetricsCorrectnessKG` if the file uses per-builder classes — exercise the live KG once with a fixed input and assert column presence + types. (Skip if the file's existing pattern doesn't apply.)

### Regression: `tests/evals/cases.yaml` + both `TOOL_BUILDERS` dicts

Two registration sites — both must be updated:

- `tests/evals/test_eval.py` — add `"gene_derived_metrics": build_gene_derived_metrics` to `TOOL_BUILDERS`.
- `tests/regression/test_regression.py` — add the same entry to its `TOOL_BUILDERS` (separate dict).

Add 2–3 representative cases to `tests/evals/cases.yaml` (single-gene, mixed-input, summary). Regenerate regression baselines:

```bash
pytest tests/regression/ --force-regen -m kg
```

### About-content tests

Per the `add-or-update-tool` skill:

- `pytest tests/unit/test_about_content.py -v` — Pydantic ↔ generated markdown consistency.
- `pytest tests/integration/test_about_examples.py -v` — YAML examples execute against live KG.

---

## About Content

**File:** `multiomics_explorer/inputs/tools/gene_derived_metrics.yaml`

Per the slice spec §"Required `mistakes` + `chaining` coverage":

- `chaining:` entries (first two are required by slice spec):
  - `"gene_derived_metrics → genes_by_numeric_metric(derived_metric_ids, bucket=[...])"` — pivot to numeric drill-down for filtering on rank/percentile/bucket.
  - `"differential_expression_by_gene → gene_derived_metrics(locus_tags)"` — annotate DE hits with non-DE evidence.
  - `"resolve_gene → gene_derived_metrics(locus_tags)"` — common entry point.
- `mistakes:` — required first bullet (slice spec §"Required `mistakes` + `chaining` coverage"):
  - *Polymorphic `value`.* "The `value` column is polymorphic — branch on each row's `value_kind` (`'numeric'` → float, `'boolean'` → `'true'`/`'false'` string, `'categorical'` → category string). Numeric rows additionally have `rank_by_metric`, `metric_percentile`, `metric_bucket` populated when their parent DM is rankable; null otherwise (e.g. `peak_time_protein_h`)."
  - *When to drill down.* "For numeric edge filtering (bucket / percentile / rank / value thresholds), pivot to `genes_by_numeric_metric`. This tool intentionally has no edge-level numeric filters."
  - *`not_matched` ≠ no DM signal.* "`not_matched` lists genes that exist in the KG but have zero DM rows *after the applied filters*. A gene with only boolean DM signal called with `value_kind='numeric'` lands in `not_matched`. Inspect the rollup props (`g.numeric_metric_count` etc. via `gene_overview`) for unfiltered availability."
  - *Single organism enforced.* "Mixing locus_tags from MED4 and NATL2A raises `ValueError`. Call once per organism."
- `examples:` — at minimum:
  - `gene_derived_metrics(['PMM1714'])` — gene with all three DM kinds (boolean + categorical + 7 numeric rows).
  - `gene_derived_metrics(['PMM1714', 'PMM0001', 'PMN2A_2128'], summary=True)` — mixed-input summary showing breakdowns plus `not_matched` plumbing under default filters.
  - `gene_derived_metrics(['PMM1714'], value_kind='boolean')` — kind-filter routing.
  - `gene_derived_metrics(['PMM1714'], compartment='vesicle')` — compartment routing.
  - Multi-step chain: `differential_expression_by_gene` (diel experiment) → top hits → `gene_derived_metrics(locus_tags=top_hits)` → top hits with `damping_ratio` rank and `vesicle_proteome_member='true'`.
- `verbose_fields:` — `treatment, light_condition, experimental_context, p_value`.

Pydantic docstring first line (per slice spec §S2 preamble hoist) echoes the polymorphic-`value` rule, since this tool's primary footgun is misinterpreting `value` (and missing the rank/p-value gating). The full first-line text is in §"Tool Signature" above.

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_gene_derived_metrics_summary()`, `build_gene_derived_metrics()` |
| 2 | Unit test | `tests/unit/test_query_builders.py` | `TestBuildGeneDerivedMetrics`, `TestBuildGeneDerivedMetricsSummary` |
| 3 | API function | `api/functions.py` | `gene_derived_metrics()` |
| 4 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 5 | Unit test | `tests/unit/test_api_functions.py` | `TestGeneDerivedMetrics` |
| 6 | MCP wrapper | `mcp_server/tools.py` | Seven breakdown models (6 narrow + 1 wide `GeneDmMetricBreakdown`) + `GeneDerivedMetricsResult`, `GeneDerivedMetricsResponse`, `gene_derived_metrics` |
| 7 | Unit test | `tests/unit/test_tool_wrappers.py` | `TestGeneDerivedMetricsWrapper` + `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | `TestGeneDerivedMetrics` (`@pytest.mark.kg`) |
| 8a | Contract | `tests/integration/test_api_contract.py` | `TestGeneDerivedMetricsContract` — pin envelope + result keys |
| 8b | Correctness | `tests/integration/test_tool_correctness_kg.py` | `TestBuildGeneDerivedMetricsCorrectnessKG` if file pattern applies |
| 9 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS`, regenerate baselines |
| 9a | Eval | `tests/evals/test_eval.py` | Add to `TOOL_BUILDERS` (separate dict from regression) |
| 10 | Eval cases | `tests/evals/cases.yaml` | Add cases |
| 11 | About content | `multiomics_explorer/inputs/tools/gene_derived_metrics.yaml` | Author YAML |
| 12 | About markdown | (generated) | `uv run python scripts/build_about_content.py gene_derived_metrics` |
| 13 | CLAUDE.md | `CLAUDE.md` | Add row to MCP Tools table |
| 14 | Code review | — | Per `.claude/skills/code-review/SKILL.md` |

Detailed bite-sized task list lives in `docs/superpowers/plans/2026-04-26-gene-derived-metrics.md` (writing-plans format) — to be authored once this spec is approved.
