# Discovery tools — DerivedMetric awareness (slice 2 + slice-3 list_* portion)

**Status:** design, awaiting user review
**Date:** 2026-04-27
**Scope:** Add DerivedMetric rollup fields and `compartment` first-class surface to 5 existing discovery tools; absorb the list-tool half of the parent spec's slice 3 (Experiment.compartment is already live on the KG, so the retrofit is now pure explorer work).

## Context

Slice 1 (`docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md`) shipped 5 new tools (`list_derived_metrics`, `gene_derived_metrics`, `genes_by_numeric_metric`, `genes_by_boolean_metric`, `genes_by_categorical_metric`) standalone — they answer DM-centric questions but the existing discovery tools are still DM-blind. An LLM browsing experiments via `list_experiments` sees rich treatment/omics breakdowns but cannot tell which experiments have rhythmicity flags, vesicle-proteome DMs, or any DM evidence at all without a `list_derived_metrics` round-trip.

Per-DerivedMetric rollups were already materialized on Experiment / Publication / OrganismTaxon during slice-1 KG work (verified live 2026-04-27):

```
Experiment.{derived_metric_count, derived_metric_gene_count,
            derived_metric_types, derived_metric_value_kinds,
            reports_derived_metric_types, compartment}
Publication.{derived_metric_count, derived_metric_gene_count,
             derived_metric_types, derived_metric_value_kinds,
             compartments}
OrganismTaxon.{derived_metric_count, derived_metric_gene_count,
               derived_metric_types, derived_metric_value_kinds,
               compartments}
Gene.{numeric_metric_count, numeric_metric_types_observed,
      classifier_flag_count, classifier_flag_types_observed,
      classifier_label_count, classifier_label_types_observed,
      compartments_observed}
```

This slice surfaces those rollups through the explorer — no KG-side rollup work required. One KG-side change *is* required: enriching two existing fulltext indexes with DM-derived tokens so `search_text` becomes a natural DM-discovery channel.

## Scope — what this slice covers

Three research questions:

- **Browse** — when listing experiments / publications / organisms, see DM presence and value-kind composition without a separate call.
- **Triage** — given a result set, see aggregate DM/compartment composition via envelope rollups.
- **Discover via search** — `list_experiments(search_text="diel amplitude")` and `list_publications(search_text="vesicle proteomics")` surface relevant DMs through enriched fulltext indexes.

Explicitly **out of scope**: DE-tool `compartment` filter (`differential_expression_by_gene` / `_by_ortholog`) — deferred until non-`whole_cell` DE lands. `geneFullText` enrichment with DM tokens — would conflate gene function with what was *measured* on the gene (`damping_ratio` is computed on every protein-quantified Waldbauer 2012 gene; tokenizing it into geneFullText returns 312 unrelated genes for `genes_by_function(search_text="damping ratio")`). Per-row per-kind DM counts on list tools — TMI; the kind-list (`derived_metric_value_kinds`) plus envelope `by_value_kind` cover the routing job.

## Tools in scope

| Tool | What changes |
|---|---|
| `gene_overview` | Per-row DM rollup; envelope `has_derived_metrics`. |
| `list_experiments` | Per-row DM rollup; per-row `compartment`; `compartment` filter param; envelope `by_value_kind`/`by_metric_type`/`by_compartment`; fulltext-search reach (via KG enrichment). |
| `list_publications` | Per-row DM rollup; per-row `compartments`; `compartment` filter param; envelope additions; fulltext-search reach. |
| `list_organisms` | Per-row DM rollup; per-row `compartments`; `compartment` filter param; envelope additions. |
| `list_filter_values` | New `filter_type` values: `metric_type`, `value_kind`, `compartment`. |

## Design decisions (locked)

### D1 — Per-row layout: unified count + value-kind list, no per-kind counts

For `list_experiments` / `list_publications` / `list_organisms`, per-row compact carries `derived_metric_count` (single int, "how rich") and `derived_metric_value_kinds` (≤3 strings, "what kinds"). Per-kind counts (`numeric_metric_count`, etc.) on those nodes would be TMI per row — the LLM uses the compact pair for routing decisions ("does this experiment have any boolean flags? → call `genes_by_boolean_metric`") and the envelope `by_value_kind` for aggregate density. `derived_metric_types` and `derived_metric_gene_count` move to verbose.

`gene_overview` is different: Gene-side rollups are KG-stored split per-kind (`numeric_metric_count` / `classifier_flag_count` / `classifier_label_count`) and the per-gene scale is small enough for verbose to carry the splits. Compact stays unified (sum + value_kinds list); verbose adds the per-kind counts and per-kind types lists.

### D2 — No new filter params on list tools beyond `compartment`

`has_derived_metrics: bool` and `metric_types: list[str]` filter params were considered and rejected. Reasons:

- **Search index covers the discovery job** (D5 below) — `list_experiments(search_text="diel amplitude")` is the natural way to find experiments with diel-amplitude DMs once tokens are indexed, and gets free score-ranking.
- **Rollup fields cover the post-result triage job** — `derived_metric_count > 0` filtering is one client-side comparison.
- **Cluster precedent** — `clustering_analysis_count` / `cluster_types` exist on the same tools today without a `cluster_type` filter param. Same pattern.

`compartment` *is* added as a filter param on list_experiments / list_publications / list_organisms because it's the natural axis for vesicle-vs-whole-cell triage and the KG already stores it as a first-class Experiment property.

### D3 — Envelope keys: `by_value_kind`, `by_metric_type`, `by_compartment`

All three list tools' summary builders gain three new frequency rollups. Cardinality is bounded:

- `by_value_kind` — ≤3 keys ({numeric, boolean, categorical})
- `by_metric_type` — bounded by total distinct metric_types in matched set (~13 today, ~100s long-term)
- `by_compartment` — bounded by compartment vocabulary (3 present today: whole_cell, vesicle, exoproteome; 5 in extended vocabulary)

Sourced from per-row props directly (no DM-table join), since the rollups are precomputed on Experiment / Publication / OrganismTaxon. For Publication and OrganismTaxon, `compartments` is a list — flatten via `apoc.coll.flatten(collect(coalesce(node.compartments, [])))` then `apoc.coll.frequencies` (mirrors the existing `cluster_types` pattern at queries_lib.py:1249).

### D4 — `gene_overview` envelope: `has_derived_metrics`

Mirrors the existing `has_clusters` envelope summary. Counts how many of the requested locus_tags carry any DM annotation (`numeric_metric_count + classifier_flag_count + classifier_label_count > 0`). Useful one-shot triage for batch routing decisions.

### D5 — KG-side fulltext enrichment

Companion KG spec (next section) adds DM-derived tokens (DM `name`, `metric_type`, `field_description`, `compartment`) to `experimentFullText` and `publicationFullText`. `geneFullText` deliberately excluded (function-vs-measurement category error). Result: `search_text` on the existing tools naturally surfaces DMs without a new param.

### D6 — `list_filter_values`: 3 new types

| Filter type | Source | Returned shape |
|---|---|---|
| `metric_type` | `MATCH (dm:DerivedMetric) WITH dm.metric_type AS v, count(*) AS c WHERE v IS NOT NULL RETURN v, c` | `[{value, count}]` (DMs per type) |
| `value_kind` | enum `{numeric, boolean, categorical}` | `[{value, count}]` (DMs per kind — current KG: 6 numeric, 6 boolean, 1 categorical) |
| `compartment` | `MATCH (e:Experiment) WITH e.compartment AS v, count(*) AS c WHERE v IS NOT NULL RETURN v, c` | `[{value, count}]` (experiments per compartment) |

Skipped (and why): `bucket` (fixed enum in tool docstring, never KG-dependent), `categories` (per-DM, already returned by `list_derived_metrics(value_kind='categorical', verbose=True)` — adding here would duplicate and lose per-DM grouping), `derived_metric_ids` (`list_derived_metrics` is the discovery tool for these), `flag` / `rankable` / `has_p_value` (trivial booleans).

### D7 — `compartment` source: Experiment property, not DerivedMetric

`compartment` filter on list tools and the `list_filter_values` `compartment` type both source from `Experiment.compartment` (and rollup `compartments` lists on Publication / OrganismTaxon), not from `DerivedMetric.compartment`. Reasoning: `Experiment.compartment` is the wet-lab fraction (the experiment's biological reality); `DerivedMetric.compartment` is derived from it. They align 1:1 in current data (verified). Using the experiment-side property keeps the filter semantics clean ("show me vesicle experiments") and avoids a DerivedMetric join in the list-tool query path.

## Architecture

Three explorer-side layers + one KG-side companion. No new files; all changes are additive edits.

| Layer | Files | Contribution |
|---|---|---|
| KG fulltext enrichment | `multiomics_biocypher_kg` repo (separate spec) | Materialize `derived_metric_search_text` on Experiment + Publication; extend two existing fulltext indexes |
| Query builders | `multiomics_explorer/kg/queries_lib.py` | Edit ~10 builders (5 detail + 5 summary) — additive RETURN columns + WHERE conditions for compartment filter |
| API functions | `multiomics_explorer/api/functions.py` | Edit 5 functions — pass through new params, surface new envelope keys |
| MCP wrappers | `multiomics_explorer/mcp_server/tools.py` | Edit 5 wrappers — extend Pydantic `{Name}Result` / `{Name}Response` models, add `compartment` param to 3 of them, add 3 new `filter_type` Literal values |
| About content inputs | `multiomics_explorer/inputs/tools/{name}.yaml` | Edit 5 YAMLs — examples + chaining + mistakes for DM-aware usage |
| About content outputs (generated) | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md` | Regenerate via `scripts/build_about_content.py` |
| CLAUDE.md | `CLAUDE.md` | Update 5 tool-table rows with DM/compartment additions |

## Per-tool changes

Concise table — full Cypher snippets land during the per-tool Phase-1 verification step (see *Workflow* below).

### `gene_overview` ([api](multiomics_explorer/api/functions.py:312), [builder](multiomics_explorer/kg/queries_lib.py:404))

```
# Per-row, compact (additions)
derived_metric_count: int       # = numeric_metric_count + classifier_flag_count + classifier_label_count
derived_metric_value_kinds: list[str]  # subset of {numeric, boolean, categorical}; computed from per-kind counts > 0

# Per-row, verbose (additions)
numeric_metric_count: int
boolean_metric_count: int       # alias for classifier_flag_count
categorical_metric_count: int   # alias for classifier_label_count
numeric_metric_types_observed: list[str]
classifier_flag_types_observed: list[str]
classifier_label_types_observed: list[str]
compartments_observed: list[str]

# Envelope (additions)
has_derived_metrics: int        # count of requested locus_tags with derived_metric_count > 0
```

**Naming subdecision (open):** KG stores `classifier_flag_count` / `classifier_label_count` (slice-1 KG-side legacy). Two options at the explorer boundary:

- **Pass-through (no alias):** API/MCP returns the KG names verbatim. Zero translation layer; consistent with `gene_derived_metrics` already shipping these names. LLM has to learn the asymmetry between this surface and `genes_by_boolean_metric` / `genes_by_categorical_metric`.
- **Alias to `boolean_metric_count` / `categorical_metric_count`:** matches the slice-1 drill-down tool naming. Translation lives in the query builder's RETURN clause. Adds a one-line mapping; gives the LLM a uniform vocabulary across the DM tool family.

Recommend the alias. Document the asymmetry as a footnote in `references/analysis/derived_metrics.md` either way.

No new params (gene_overview is locus_tag-driven; no filter param fits).

### `list_experiments` ([api](multiomics_explorer/api/functions.py:826), [builder](multiomics_explorer/kg/queries_lib.py:1114))

```
# Per-row, compact (additions)
derived_metric_count: int
derived_metric_value_kinds: list[str]
compartment: str | None         # from Experiment.compartment

# Per-row, verbose (additions)
derived_metric_gene_count: int
derived_metric_types: list[str]
reports_derived_metric_types: list[str]   # sparse — see KG schema; typically equals derived_metric_types

# Envelope (additions)
by_value_kind: list[{value_kind, count}]
by_metric_type: list[{metric_type, count}]
by_compartment: list[{compartment, count}]

# New filter param
compartment: str | None         # 'whole_cell' | 'vesicle' | 'exoproteome' | 'spent_medium' | 'lysate'
```

Cypher delta for compartment WHERE clause (mirrors `treatment_type` pattern):

```cypher
WHERE ($compartment IS NULL OR e.compartment = $compartment)
```

`reports_derived_metric_types` is verbose-only because for current data it duplicates `derived_metric_types`; surfacing both lets the LLM diagnose if/when an experiment imports DMs computed from another paper's data (today: no such case).

### `list_publications` ([api](multiomics_explorer/api/functions.py:686), [builder](multiomics_explorer/kg/queries_lib.py:760))

```
# Per-row, compact (additions)
derived_metric_count: int
derived_metric_value_kinds: list[str]
compartments: list[str]         # from Publication.compartments (rollup list)

# Per-row, verbose (additions)
derived_metric_gene_count: int
derived_metric_types: list[str]

# Envelope (additions)
by_value_kind: list[{value_kind, count}]
by_metric_type: list[{metric_type, count}]
by_compartment: list[{compartment, count}]

# New filter param
compartment: str | None
```

Compartment filter semantics: `WHERE $compartment IS NULL OR $compartment IN p.compartments`. Filters the publication if it has at least one experiment in that compartment.

### `list_organisms` ([api](multiomics_explorer/api/functions.py:574), [builder](multiomics_explorer/kg/queries_lib.py:935))

```
# Per-row, compact (additions)
derived_metric_count: int
derived_metric_value_kinds: list[str]
compartments: list[str]

# Per-row, verbose (additions)
derived_metric_gene_count: int
derived_metric_types: list[str]

# Envelope (additions)
by_value_kind: list[{value_kind, count}]
by_metric_type: list[{metric_type, count}]
by_compartment: list[{compartment, count}]

# New filter param
compartment: str | None
```

`list_organisms` returns ~30 rows; envelope rollups still earn their tokens as a triage signal across the full set (e.g. "of 30 organisms, 4 have DM evidence, all in vesicle compartment").

### `list_filter_values` ([api](multiomics_explorer/api/functions.py:528), [builder](multiomics_explorer/kg/queries_lib.py:896))

```python
# New filter_type values (Literal in MCP wrapper)
filter_type: Literal["gene_category", "brite_tree", "growth_phase",
                     "metric_type", "value_kind", "compartment"]
```

Three new query builders (mirror existing `build_list_gene_categories` / `build_list_brite_trees`):

```python
def build_list_metric_types() -> tuple[str, dict]:
    """List distinct DerivedMetric.metric_type values with counts.

    RETURN keys: value, count.
    """
    return (
        "MATCH (dm:DerivedMetric) WHERE dm.metric_type IS NOT NULL\n"
        "RETURN dm.metric_type AS value, count(*) AS count\n"
        "ORDER BY count DESC, value",
        {},
    )

def build_list_value_kinds() -> tuple[str, dict]:
    """List DerivedMetric.value_kind enum with DM counts per kind.

    RETURN keys: value, count.
    """
    return (
        "MATCH (dm:DerivedMetric) WHERE dm.value_kind IS NOT NULL\n"
        "RETURN dm.value_kind AS value, count(*) AS count\n"
        "ORDER BY count DESC, value",
        {},
    )

def build_list_compartments() -> tuple[str, dict]:
    """List distinct Experiment.compartment values with experiment counts.

    Uses Experiment as the source-of-truth (D7) — wet-lab fraction.

    RETURN keys: value, count.
    """
    return (
        "MATCH (e:Experiment) WHERE e.compartment IS NOT NULL\n"
        "RETURN e.compartment AS value, count(*) AS count\n"
        "ORDER BY count DESC, value",
        {},
    )
```

Wrapper dispatch in `list_filter_values` adds three `elif` branches matching the existing `gene_category` / `brite_tree` / `growth_phase` shape.

## KG companion spec

**File:** `docs/kg-specs/2026-04-27-derived-metric-fulltext-enrichment.md`

**Summary:** Add `derived_metric_search_text: str` property on Experiment + Publication, and extend `experimentFullText` + `publicationFullText` indexes to include it. Tokens come from each node's reachable DerivedMetrics: `name`, `metric_type` (snake_case → space-tokenized for human-search compatibility, e.g. `damping ratio`), `field_description`, `compartment`.

**Current state (verified 2026-04-27):**
- `experimentFullText` indexes Experiment.{name, treatment, control, experimental_context, light_condition}
- `publicationFullText` indexes Publication.{title, abstract, description}
- `geneFullText` indexes Gene.{gene_summary, all_identifiers, gene_name_synonyms, alternate_functional_descriptions} — **not changed**
- 13 DerivedMetric nodes; per-experiment DM rollup props already materialized

**Required changes:**

| Node | Property | Change |
|---|---|---|
| Experiment | `derived_metric_search_text` | new (computed during post-import: aggregate DM tokens for DMs reported by experiment) |
| Publication | `derived_metric_search_text` | new (computed during post-import: aggregate across publication's experiments) |

**Index changes:**

| Index | Action | Properties (after) |
|---|---|---|
| `experimentFullText` | drop + recreate | name, treatment, control, experimental_context, light_condition, **derived_metric_search_text** |
| `publicationFullText` | drop + recreate | title, abstract, description, **derived_metric_search_text** |
| `geneFullText` | unchanged | (intentional — see *Out of scope*) |

**Verification queries (post-rebuild):**

```cypher
// Confirm new property is populated
MATCH (e:Experiment) WHERE e.derived_metric_count > 0
RETURN count(*) AS experiments_with_dms,
       count(e.derived_metric_search_text) AS experiments_with_search_text
// Expect: equal counts

// Confirm DM-token search returns matched experiments
CALL db.index.fulltext.queryNodes('experimentFullText', 'diel amplitude')
YIELD node, score
RETURN count(*) AS hits
// Expect: ≥ Waldbauer 2012's experiment count (DMs include `diel_amplitude_*`)

// Confirm geneFullText unchanged (regression guard)
SHOW FULLTEXT INDEXES YIELD name, properties
WHERE name = 'geneFullText'
RETURN properties
// Expect: gene_summary, all_identifiers, gene_name_synonyms, alternate_functional_descriptions
```

**Coordination:** This KG spec must land *before* the explorer-side fulltext-relying tests can be written. Other slice-2 work (rollup fields, envelope keys, compartment filter, `list_filter_values` types) is unblocked by the KG state already live as of 2026-04-27 and can proceed in parallel with the KG enrichment.

## Cross-cutting validation

| Situation | Behavior |
|---|---|
| `compartment` filter receives value not in `Experiment.compartment` distinct set | No special validation — pass through; empty result is correct semantics. (Mirrors how `treatment_type` filter handles unknown values today.) |
| `list_filter_values(filter_type='metric_type')` against current KG | Returns 13 rows (per slice-1 baseline) |
| `list_filter_values(filter_type='value_kind')` | Returns 3 rows: numeric/boolean/categorical with current counts |
| `list_filter_values(filter_type='compartment')` | Returns 3 rows today: whole_cell/vesicle/exoproteome (extended vocabulary `{spent_medium, lysate}` returns 0 rows until paper lands) |
| Backwards compat | All changes additive: new optional params, new RETURN columns, new envelope keys. No renames, no removed columns. Existing callers see no breaking change. |

## Testing

Per the `testing` skill — three layers, mirrors slice-1 patterns.

### Unit tests (no Neo4j)

`tests/unit/test_query_builders.py` — extend existing `TestBuild{Name}` classes (5 of them) with assertions for new RETURN columns and the `compartment` WHERE clause. Add `TestBuildListMetricTypes` / `TestBuildListValueKinds` / `TestBuildListCompartments`.

`tests/unit/test_api_functions.py` — extend existing `Test{Name}` classes with mocked `GraphConnection`. Cover:
- New envelope keys present (`by_value_kind`, `by_metric_type`, `by_compartment`)
- New per-row fields present (compact + verbose)
- `compartment` filter param plumbing (3 list tools)
- `gene_overview` envelope `has_derived_metrics` arithmetic
- `list_filter_values` dispatching to the 3 new builders

`tests/unit/test_tool_wrappers.py` — extend existing `Test{Name}Wrapper` classes. Update `EXPECTED_TOOLS`, Pydantic field assertions for new model fields, Literal expansion check for `filter_type`.

### KG integration tests

`tests/integration/test_mcp_tools.py` — extend `TestListExperiments` / `TestListPublications` / `TestListOrganisms` / `TestGeneOverview` / `TestListFilterValues` with happy-path assertions. Pinned baselines (2026-04-27):

- `list_experiments(compartment='vesicle')` → 5 results
- `list_experiments(compartment='exoproteome')` → 7 results
- `list_filter_values(filter_type='metric_type')` → 13 distinct values
- `list_filter_values(filter_type='value_kind')` → 3 rows: `{numeric: 6, boolean: 6, categorical: 1}`
- `list_filter_values(filter_type='compartment')` → 3 rows: `{whole_cell: 160, exoproteome: 7, vesicle: 5}`
- `gene_overview(locus_tags=[<biller-2018 gene>])` → row has `derived_metric_count > 0` and `derived_metric_value_kinds` includes `boolean`/`categorical`
- `list_publications(search_text="diel amplitude")` → matches Waldbauer 2012 once fulltext enrichment lands (DM names like `diel_amplitude_protein_log2` token-split into `diel`, `amplitude`, `protein`, `log2` during indexing)

### Fulltext-search assertions (gated on KG enrichment)

- `list_experiments(search_text="vesicle")` → returns Biller 2018 vesicle experiments via the new DM tokens (the 5 KG-side `compartment="vesicle"` experiments). Pin once KG enrichment is verified live.
- `list_publications(search_text="damping ratio")` → matches Waldbauer 2012 via tokenized DM `metric_type` `damping_ratio`.
- `genes_by_function(search_text="damping ratio")` → does **not** match every protein-quantified gene (regression guard for the `geneFullText` category-error decision in D5; assert hit count is bounded by what was already matching before slice 2).

### Regression

- Add cases to `tests/evals/cases.yaml` covering: `compartment` filter on each list tool; new `filter_type` values; gene_overview with DM-rich gene set.
- Existing TOOL_BUILDERS rows need refreshed baselines because RETURN columns expanded — run `pytest tests/regression/ --force-regen -m kg` after the builders land.

### About-content tests

Run per the `add-or-update-tool` skill:
- `pytest tests/unit/test_about_content.py -v` (Pydantic ↔ generated markdown consistency)
- `pytest tests/integration/test_about_examples.py -v` (YAML examples execute against live KG)

## Documentation

Per the `add-or-update-tool` skill — no hand-written tool docs:

1. Edit `multiomics_explorer/inputs/tools/{name}.yaml` × 5. New examples + `mistakes` + `chaining` entries focused on:
   - **Routing via value_kinds.** "If a row has `derived_metric_value_kinds=['boolean']`, drill down via `genes_by_boolean_metric`. For `['numeric']`, use `genes_by_numeric_metric`."
   - **Triage via envelope.** Show how `by_value_kind` / `by_compartment` summarize a result set.
   - **Search-text reach.** "After the fulltext enrichment lands, `list_experiments(search_text='rhythmicity')` surfaces Biller 2018 experiments via DM tokens — no need to call `list_derived_metrics` first."
   - **`compartment` filter.** Examples for vesicle / exoproteome / whole_cell scoping.
   - **`list_filter_values` discovery.** Examples for the 3 new filter types.

2. Regenerate via `uv run python scripts/build_about_content.py {name}` × 5.

3. Update `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/derived_metrics.md` (slice-1 hand-authored ref) with a *Discovery patterns* section showing the new search-text + rollup workflow. Note the KG-side naming asymmetry surfaced in `gene_overview` (KG has `classifier_flag_count` / `classifier_label_count`; API returns `boolean_metric_count` / `categorical_metric_count`).

4. CLAUDE.md MCP Tools table: update the 5 affected rows in place. No new rows.

## Workflow — Phase 1 / Phase 2 per tool

Per the `add-or-update-tool` skill, each of the 5 tools is a *modify existing* operation. Single-spec design (this doc) replaces per-tool Phase-1 specs because the change shape is uniform — but each tool still goes through the gated build:

**Phase 1 (one-time, this doc):**
- Scope, KG verification, design — done.
- Verified Cypher deltas captured in *Per-tool changes* above.
- → User approves this design.

**Phase 2 (per tool, parallelizable):** for each tool, the standard 4-layer build with specialized agents:

1. `query-builder` agent — extend builder + summary builder.
2. `api-updater` agent — extend API function + envelope assembly.
3. `tool-wrapper` agent — extend Pydantic models + wrapper signature + Literal expansion.
4. `doc-updater` agent (parallel with `test-updater`) — edit YAML + regenerate about content + update CLAUDE.md row.
5. `test-updater` agent (parallel with `doc-updater`) — extend test classes across 3 unit files + integration.
6. `code-reviewer` agent — last, against this spec + layer-rules.

Per the skill: spec frozen after approval — adding fields or changing query shape during build requires re-approval.

KG companion spec follows its own track: write spec → user coordinates with `multiomics_biocypher_kg` → rebuild → verify queries → enable fulltext-search test assertions in slice 2.

## Order of work

1. **This spec approved.**
2. **KG companion spec written and approved** (`docs/kg-specs/2026-04-27-derived-metric-fulltext-enrichment.md`) — separate review thread.
3. **Explorer-side rollups + compartment** (Phase 2 across 5 tools) can proceed without waiting for KG enrichment — those props are already live.
4. **KG enrichment lands** (separate workstream in `multiomics_biocypher_kg`).
5. **Fulltext-search test assertions** un-gated, baselines pinned.
6. **Slice 2 closes.**

## Out of scope (deferred)

- **DE-tool `compartment` filter** on `differential_expression_by_gene` / `_by_ortholog` — slice-3 tail. Deferred until non-`whole_cell` DE lands; only `whole_cell` DE exists today.
- **`geneFullText` DM enrichment** — would conflate gene function with what was *measured* on the gene. Tracked in this spec as a deliberate negative scope; revisit only if a gene-side DM-search use case emerges that doesn't introduce the function/measurement category error.
- **Per-row per-kind DM counts on list tools** — TMI; rollup unified count + value_kinds list + envelope `by_value_kind` cover the routing job.
- **`has_derived_metrics: bool` filter param on list tools** — covered by client-side filtering on `derived_metric_count > 0` and by the search-text path; revisit if usage shows it's a hot path.
- **Cross-evidence integration** (DM + DE + clusters in one view) — out of scope here as in slice 1.
