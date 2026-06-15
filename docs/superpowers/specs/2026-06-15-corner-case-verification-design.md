# Corner-case verification harness — design

**Date:** 2026-06-15
**Status:** approved (design); pending implementation plan
**Author:** Osnat + Claude

## Motivation

Two explorer bugs of the same class shipped recently:

1. **Organism resolver gated genomic queries on expression data.**
   `_validate_organism_inputs` resolved organisms by matching `Experiment`
   nodes with `gene_count > 0`, so genome-only and metabolomics-only strains
   were unresolvable — every single-organism genomic tool raised
   `no organism matching '<name>' found`. Fixed 2026-06-14 (resolve via
   `OrganismTaxon.preferred_name`).
2. **Index error on `Changes_expression_of` when an entity has no
   experiments.** A query result was indexed `[0]` on a non-aggregating query
   that returns zero rows when the entity has no expression edges.

Both are the **empty/sparse data-layer** class: a tool assumes a data layer
(experiments/expression, orthologs, chemistry, derived metrics, clusters,
metabolomics) is populated, but the KG now holds entities where that layer is
empty. Recent KG rebuilds made this systemic — 11 genome-only organisms
(`experiment_count = 0`, genes present) and several organisms with experiments
but no transcriptomic layer (PROTEOMICS / METABOLOMICS / VESICLE_PROTEOMICS
only) now exist.

Existing tests assert biological correctness on well-populated entities
(MED4 etc.). They do not systematically exercise degenerate-but-valid inputs,
so this whole class slips through.

## Goal

A **durable, CI-permanent** verification harness that systematically exercises
every MCP tool against degenerate-but-valid inputs and asserts structural
invariants — plus a one-time fix of every bug it (and a static sweep) surfaces.

### Coverage axes (v1)

1. **Empty/sparse data layer** — valid entity lacking a layer (genome-only
   strain, expression-layer-empty strain, gene with no DE / no orthologs /
   no chemistry / no DMs / no clusters). *Primary; the class behind both bugs.*
2. **Missing & mixed-batch entities** — unknown
   locus_tags/organism/experiment_ids/DOIs/metabolite_ids, and batches mixing
   valid + invalid (`not_found` / `not_matched` correctness, no crash).
3. **Pagination & filter-empty boundaries** — `offset` past end, limit edges,
   filter combinations that legitimately yield zero rows (rankable-gated on
   non-rankable, exclude-all).
4. **Null-valued properties** — layers present but key props null (`strand`
   ~50% null, `background_factors`, `growth_phase`) — coalesce / None-safety
   in summaries and filters.

## Key insight: invariant oracle

For degenerate inputs you usually cannot assert specific biology. The harness
therefore asserts **structural invariants** that must hold for *every* tool on
*every* input, including degenerate ones. This is the oracle that makes
systematic corner-case testing tractable.

## Architecture

Three components under `tests/integration/edge_cases/`, plus a one-time sweep.

### 1. Edge-case input bank — `tests/integration/edge_cases/fixtures.py`

A registry of pinned, KG-discovered degenerate inputs, keyed by *semantic input
type*. Each fixture carries a one-line comment stating why it is degenerate.

Concrete values discovered against the live KG (2026-06-15):

- **Organism layers**
  - `GENOME_ONLY = "Prochlorococcus MIT9515"` — `experiment_count = 0`, 1949
    genes (11 such strains exist).
  - `EXPRESSION_LAYER_EMPTY = "Prochlorococcus MIT0801"` — 6 experiments,
    METABOLOMICS-only (Experiment nodes exist, no DE edges).
  - proteomics-only variant (e.g. `"Synechococcus WH7803"`, 69 experiments,
    PROTEOMICS/EXOPROTEOMICS).
  - `CONTROL = "Prochlorococcus MED4"` — fully populated, sanity baseline.
- **Genes** — gene with no DE; gene with no orthologs; gene with no chemistry;
  gene with no DMs; gene with no clusters; `UNKNOWN_LOCUS = "PMM_FAKE"`;
  `MIXED_BATCH = [<real>, "PMM_FAKE"]`; `CROSS_ORG_BATCH` (expects documented
  `ValueError`).
- **Other ID types** — unknown / mixed `experiment_ids`, `publication_dois`,
  `metabolite_ids`, homolog group ids, cluster / analysis ids, derived_metric
  ids, ontology term ids.
- **Pagination / filter-empty** — `OFFSET_PAST_END`; filter combos yielding
  zero rows (rankable-gated filter on a non-rankable DM; exclude-all set).
- **Null props** — anchors whose `strand` / `background_factors` /
  `growth_phase` are null.

**Self-validation.** A guard test asserts each fixture still has its degenerate
property after every KG rebuild (e.g. `GENOME_ONLY` still has
`experiment_count == 0`). This keeps the bank honest across rebuilds without
resorting to runtime fuzzing — if a rebuild populates a previously-empty layer,
the guard fails loudly and we re-pin.

### 2. Invariant oracle — `tests/integration/edge_cases/invariants.py`

A single `assert_tool_invariants(tool_name, response, inputs, *, expects_error)`
applied to every (tool × edge-input) cell:

- **No unhandled exception.** Only inputs explicitly flagged `expects_error`
  (e.g. cross-organism batch) may raise; the raise is then asserted to be the
  documented `ValueError`, not an arbitrary crash.
- **Schema validity.** The response validates against the tool's Pydantic
  response model.
- **Count consistency.** `total_matching == len(results)` when `truncated`
  is false; all counts ≥ 0.
- **Batch-diagnostic correctness.** `not_found` and `not_matched` are subsets
  of the inputs and disjoint from matched ids; found ∪ not_found ∪ not_matched
  partitions the input as the tool documents.
- **Empty-layer shape.** An empty layer yields empty `results` plus
  zeroed/empty rollups — not a crash, not a malformed envelope.

Invariants are applied à la carte: a tool that has no batch inputs skips the
batch-diagnostic check. The applicable invariant set is derived from the tool's
declared input-types (see component 3).

### 3. Tool matrix runner — `tests/integration/test_edge_case_contracts.py`

A parametrized test that, per tool, declares the semantic input-types it
consumes via a small **explicit map** (`TOOL_INPUT_TYPES`) — chosen over
signature introspection for legibility and intent. For each tool it selects the
relevant edge fixtures and runs the tool through the oracle.

- New tools add one line to `TOOL_INPUT_TYPES`.
- A meta-test fails if any registered tool (from the existing `EXPECTED_TOOLS`
  registry) is absent from `TOOL_INPUT_TYPES` — mirrors the existing
  registration gate so coverage cannot silently lapse.

## One-time static sweep + find/fix loop

Before / alongside the harness:

- **C-sweep.** AST/grep audit of `execute_query(...)[0]` and `[0]["..."]`
  call sites in `api/functions.py` (and anywhere else), classifying each as
  aggregating (returns exactly one row — safe) vs. non-aggregating (zero rows
  on empty — crash risk). Confirmed crashers — including the known
  `Changes_expression_of` index error — get fixed with a targeted regression
  test immediately (TDD).
- **Harness find/fix.** Every failure the harness surfaces is fixed TDD-style
  (the failing invariant is the red test). If a failure reveals a *design*
  question rather than a clear bug (e.g. "should an empty layer return an
  explanatory warning, not just empty?"), it is cataloged in the Open
  Questions section below rather than force-fixed in this effort.

## Scope boundaries (YAGNI)

- **No generative fuzzing in v1.** The self-validating curated bank covers the
  discovery need; fuzzing is deferred (possible later supplement).
- **No unit-layer mirror.** These are integration contracts against the live
  KG (`@pytest.mark.kg`); they are not duplicated with mocked connections.
- **No biological-correctness re-testing.** Only structural invariants. The
  KG remains the source of truth for biology.
- **No new tool behavior** beyond bug fixes the sweep/harness justify.

## Testing

- All harness tests are `@pytest.mark.kg` integration tests; they run in the
  existing `pytest -m kg` lane.
- Bug fixes surfaced by the sweep get focused regression tests in their tools'
  existing integration classes (in addition to the harness coverage).
- The fixture self-validation guard runs in the same lane and gates KG-rebuild
  reconciliation.

## Open questions

(To be filled during implementation as design-vs-bug judgment calls arise.)

## Out of scope / future

- Generative/property-based fuzzing as a supplemental discovery lane.
- Extending invariants to performance/latency budgets.
