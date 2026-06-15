# Corner-case Verification Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a durable, CI-permanent harness that exercises every MCP tool against degenerate-but-valid inputs and asserts structural invariants, and fix every bug it (plus a one-time static sweep) surfaces.

**Architecture:** Three components under `tests/integration/edge_cases/` — a KG-discovered fixture bank (with a self-validation guard), a defensive invariant oracle, and a parametrized matrix runner that drives each tool through per-tool scenario builders. A one-time static sweep (Phase 0) classifies `execute_query(...)[0]` sites and fixes non-aggregating crashers first.

**Tech Stack:** Python 3.13, pytest (`@pytest.mark.kg`), FastMCP tool wrappers, Pydantic response models, Neo4j (live KG at localhost:7687), `uv run`.

**Reference spec:** `docs/superpowers/specs/2026-06-15-corner-case-verification-design.md`

---

## Conventions used throughout

- **Two call layers.** API layer returns dicts: `api.<fn>(..., conn=conn)`.
  Wrapper layer returns Pydantic models and raises `ToolError`:
  `await tool_fns[name](ctx, ...)` where `ctx = _ctx_with_conn(conn)`.
  The harness drives the **wrapper layer** (it is what Claude Code calls, and
  Pydantic construction is itself a contract check).
- **Run unit tests:** `uv run pytest <path> -v`
- **Run KG tests:** `uv run pytest <path> -v -m kg` (needs Neo4j up).
- **Commit cadence:** every task ends with a commit. Branch is
  `fix/organism-resolver-genome-only` (current) unless told otherwise.

---

## Phase 0 — Static crash sweep (independent value)

Finds and fixes the `[0]`-index-on-empty-result crash class, including the
known `Changes_expression_of` bug. Ships value without the harness.

### Task 0.1: Inventory and classify `[0]` indexing sites

**Files:**
- Create: `docs/superpowers/scoping/2026-06-15-index-sweep.md` (working notes)

- [ ] **Step 1: Generate the candidate list**

Run:
```bash
cd /home/osnat/github/multiomics_explorer
grep -rn "execute_query(.*)\[0\]\|)\[0\]\[" \
  multiomics_explorer/api/functions.py \
  multiomics_explorer/mcp_server/tools.py \
  multiomics_explorer/analysis/*.py > /tmp/index_sites.txt
wc -l /tmp/index_sites.txt
```
Expected: a list of ~40+ call sites (api/functions.py dominates).

- [ ] **Step 2: Classify each site**

For each site, open the file and read the Cypher passed to that
`execute_query`. Classify:
- **SAFE (aggregating):** the `RETURN` uses an aggregation
  (`count(...)`, `collect(...)`, `apoc.coll.frequencies(...)`) with no
  grouping key, OR is already guarded by `if rows:` / `[0] if rows else ...`.
  Aggregations return exactly one row even on empty input.
- **RISK (non-aggregating):** the `RETURN` projects per-row values from a
  `MATCH`/`OPTIONAL MATCH` with no aggregation, so zero matches ⇒ zero rows ⇒
  `[0]` raises `IndexError`.

Record each site in the scoping doc as a table: `file:line | classification |
the entity-with-no-data input that triggers it`.

- [ ] **Step 3: Commit the inventory**

```bash
git add docs/superpowers/scoping/2026-06-15-index-sweep.md
git commit -m "docs(scoping): inventory of [0]-index call sites for crash sweep"
```

### Task 0.2: Reproduce + fix each RISK site (repeat per confirmed crasher)

Do this task once per site classified RISK in Task 0.1. The known
`Changes_expression_of` bug is one instance — confirm its exact site here.

**Files:**
- Modify: `multiomics_explorer/api/functions.py` (or the offending file) at the RISK line
- Test: the offending tool's existing integration class in
  `tests/integration/test_mcp_tools.py`

- [ ] **Step 1: Write a failing regression test reproducing the crash**

Add to the offending tool's integration test class (substitute the real tool
name, the degenerate input that triggers it, and the expected empty-shape
assertions). Example shape for an expression tool against a genome-only strain:

```python
    @pytest.mark.kg
    def test_<tool>_genome_only_strain_no_crash(self, conn):
        # Genome-only strain: genes present, zero Experiment / DE edges.
        # Previously raised IndexError on result[0].
        result = api.<tool>(organism="Prochlorococcus MIT9515", conn=conn)
        assert result["results"] == []
        assert result["total_matching"] == 0
```

- [ ] **Step 2: Run it; verify it fails with IndexError**

Run: `uv run pytest tests/integration/test_mcp_tools.py -k "<tool>_genome_only" -v -m kg`
Expected: FAIL with `IndexError: list index out of range` at the RISK line.

- [ ] **Step 3: Fix the site**

Replace the unguarded index with an empty-safe form. Pattern:

```python
# before
row = conn.execute_query(cypher, **params)[0]
value = row["field"]

# after
rows = conn.execute_query(cypher, **params)
row = rows[0] if rows else {}
value = row.get("field", <empty-default>)   # [] for lists, 0 for counts, {} for maps
```

If many fields read off `row`, build the empty default explicitly so the
envelope shape matches a normal empty result (lists `[]`, counts `0`).

- [ ] **Step 4: Run it; verify it passes and no other tests regress**

Run: `uv run pytest tests/integration/test_mcp_tools.py -k "<tool>" -v -m kg`
Expected: PASS, including pre-existing tests for that tool.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/ tests/integration/test_mcp_tools.py
git commit -m "fix(<tool>): empty-safe result indexing for no-data entities"
```

### Task 0.3: Phase-0 changelog entry

**Files:**
- Modify: `CHANGELOG.md` (under `## [Unreleased]` → `### Fixed`)

- [ ] **Step 1: Add the entry**

```markdown
- Empty-safe result indexing across expression/data-layer tools: querying a
  valid entity that lacks a data layer (genome-only strain, gene with no DE,
  …) no longer raises `IndexError` — these now return an empty envelope.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): log empty-safe indexing fixes"
```

---

## Phase 1 — Fixture bank + self-validation guard

### Task 1.1: Create the edge-case fixture bank

**Files:**
- Create: `tests/integration/edge_cases/__init__.py` (empty)
- Create: `tests/integration/edge_cases/fixtures.py`

- [ ] **Step 1: Write the fixture module**

Each constant is a pinned value with a one-line comment on why it is
degenerate. Use the discovery cypher in comments so re-pinning after a rebuild
is mechanical. Create `tests/integration/edge_cases/__init__.py` empty, then
`fixtures.py`:

```python
"""Pinned, KG-discovered degenerate inputs for the corner-case harness.

Each fixture is degenerate in exactly one way. The companion guard test
(test_fixture_guards.py) asserts each still has its degenerate property after a
KG rebuild; if a rebuild populates a previously-empty layer, the guard fails
and the fixture must be re-pinned using the discovery cypher in its comment.
"""

# --- Organisms by data-layer population -----------------------------------

# experiment_count == 0, genes present. 11 such strains as of 2026-06-15.
# MATCH (o:OrganismTaxon) WHERE coalesce(o.experiment_count,0)=0
#   AND coalesce(o.gene_count,0)>0 RETURN o.preferred_name LIMIT 1
GENOME_ONLY_ORGANISM = "Prochlorococcus MIT9515"

# Has Experiment nodes but METABOLOMICS-only — no transcriptomic / DE layer.
# MATCH (o:OrganismTaxon) WHERE o.experiment_count>0
#   AND o.omics_types=['METABOLOMICS'] RETURN o.preferred_name LIMIT 1
EXPRESSION_LAYER_EMPTY_ORGANISM = "Prochlorococcus MIT0801"

# Fully populated control for sanity baselines.
CONTROL_ORGANISM = "Prochlorococcus MED4"

# --- Genes by layer -------------------------------------------------------

# Valid MED4 gene with zero Changes_expression_of edges.
# MATCH (g:Gene {organism_name:'Prochlorococcus MED4'})
#   WHERE NOT EXISTS { (:Experiment)-[:Changes_expression_of]->(g) }
#   RETURN g.locus_tag LIMIT 1
GENE_NO_DE = "PMM1720"

# Unknown locus tag (never present).
UNKNOWN_LOCUS = "PMM_DOES_NOT_EXIST"

# Real + fake mix for not_found correctness (single organism).
MIXED_LOCUS_BATCH = ["PMM0001", "PMM_DOES_NOT_EXIST"]

# --- Other unknown IDs (for not_found buckets) ----------------------------

UNKNOWN_EXPERIMENT_ID = "exp_does_not_exist"
UNKNOWN_PUBLICATION_DOI = "10.0000/does.not.exist"
UNKNOWN_METABOLITE_ID = "kegg.compound:C99999"
UNKNOWN_HOMOLOG_GROUP = "cyanorak:CK_99999999"
UNKNOWN_CLUSTER_ID = "cluster_does_not_exist"
UNKNOWN_DERIVED_METRIC_ID = "dm_does_not_exist"
UNKNOWN_ONTOLOGY_TERM = "go:9999999"

# --- Pagination -----------------------------------------------------------

OFFSET_PAST_END = 10_000_000
```

> NOTE for the implementer: before pinning `GENE_NO_DE` and the unknown IDs,
> run each comment's discovery cypher via the `run_cypher` MCP tool (or
> `uv run multiomics-explorer cypher "..."`) to confirm the value behaves as
> described against the *current* KG. Replace any that drift.

- [ ] **Step 2: Commit**

```bash
git add tests/integration/edge_cases/__init__.py tests/integration/edge_cases/fixtures.py
git commit -m "test(edge): add KG-discovered degenerate fixture bank"
```

### Task 1.2: Fixture self-validation guard

**Files:**
- Create: `tests/integration/edge_cases/test_fixture_guards.py`

- [ ] **Step 1: Write the guard tests**

```python
import pytest
from tests.integration.edge_cases import fixtures as fx


@pytest.mark.kg
class TestFixtureGuards:
    """Assert each fixture still has its degenerate property. A failure here
    means a KG rebuild changed the fixture's nature — re-pin it."""

    def test_genome_only_has_no_experiments(self, conn):
        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon {preferred_name:$n}) "
            "RETURN coalesce(o.experiment_count,0) AS e, "
            "coalesce(o.gene_count,0) AS g",
            n=fx.GENOME_ONLY_ORGANISM,
        )
        assert rows, f"{fx.GENOME_ONLY_ORGANISM} no longer in KG"
        assert rows[0]["e"] == 0
        assert rows[0]["g"] > 0

    def test_expression_layer_empty_has_experiments_no_de(self, conn):
        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon {preferred_name:$n}) "
            "RETURN coalesce(o.experiment_count,0) AS e, "
            "coalesce(o.omics_types,[]) AS omics",
            n=fx.EXPRESSION_LAYER_EMPTY_ORGANISM,
        )
        assert rows, f"{fx.EXPRESSION_LAYER_EMPTY_ORGANISM} no longer in KG"
        assert rows[0]["e"] > 0
        assert "TRANSCRIPTOMICS" not in [o.upper() for o in rows[0]["omics"]]

    def test_gene_no_de_has_no_expression_edge(self, conn):
        rows = conn.execute_query(
            "MATCH (g:Gene {locus_tag:$lt}) "
            "RETURN EXISTS { (:Experiment)-[:Changes_expression_of]->(g) } AS de",
            lt=fx.GENE_NO_DE,
        )
        assert rows, f"{fx.GENE_NO_DE} no longer in KG"
        assert rows[0]["de"] is False

    def test_unknown_ids_truly_absent(self, conn):
        rows = conn.execute_query(
            "RETURN EXISTS { (g:Gene {locus_tag:$lt}) } AS gene_exists",
            lt=fx.UNKNOWN_LOCUS,
        )
        assert rows[0]["gene_exists"] is False
```

- [ ] **Step 2: Run; verify all pass against current KG**

Run: `uv run pytest tests/integration/edge_cases/test_fixture_guards.py -v -m kg`
Expected: PASS. If any fail, re-pin the offending fixture in `fixtures.py`
using its discovery cypher, then re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/edge_cases/test_fixture_guards.py
git commit -m "test(edge): self-validation guard for degenerate fixtures"
```

---

## Phase 2 — Invariant oracle

### Task 2.1: Write the defensive invariant oracle

**Files:**
- Create: `tests/integration/edge_cases/invariants.py`

- [ ] **Step 1: Write the oracle**

Defensive: each invariant runs only when the corresponding attribute exists,
because envelope shapes differ across tools (and `not_found` is sometimes a
flat `list[str]`, sometimes a structured submodel).

```python
"""Structural invariants every tool response must satisfy on any input,
including degenerate ones. Operates on Pydantic wrapper responses."""


def _get(resp, name):
    return getattr(resp, name, None)


def assert_envelope_invariants(label, resp):
    """Assert universal envelope invariants. Skips checks for fields a given
    response model does not declare."""
    results = _get(resp, "results")
    total_matching = _get(resp, "total_matching")
    returned = _get(resp, "returned")
    truncated = _get(resp, "truncated")

    if results is not None:
        assert isinstance(results, list), f"{label}: results not a list"

    # returned == len(results)
    if returned is not None and results is not None:
        assert returned == len(results), (
            f"{label}: returned={returned} != len(results)={len(results)}"
        )

    # counts non-negative
    for cname in ("total_matching", "returned", "total_entries"):
        cval = _get(resp, cname)
        if cval is not None:
            assert cval >= 0, f"{label}: {cname}={cval} < 0"

    # not-truncated ⇒ everything matching is on this page
    if truncated is False and total_matching is not None and returned is not None:
        assert returned <= total_matching, (
            f"{label}: not truncated but returned={returned} "
            f"> total_matching={total_matching}"
        )


def assert_batch_diagnostics(label, resp, input_ids):
    """not_found / not_matched (when flat lists) ⊆ inputs and disjoint."""
    nf = _get(resp, "not_found")
    nm = _get(resp, "not_matched")
    input_set = {str(x).lower() for x in input_ids}

    if isinstance(nf, list):
        for x in nf:
            assert str(x).lower() in input_set, (
                f"{label}: not_found id {x!r} not in inputs"
            )
    if isinstance(nm, list):
        for x in nm:
            assert str(x).lower() in input_set, (
                f"{label}: not_matched id {x!r} not in inputs"
            )
    if isinstance(nf, list) and isinstance(nm, list):
        assert set(map(str, nf)).isdisjoint(map(str, nm)), (
            f"{label}: not_found and not_matched overlap"
        )


def assert_empty_layer_shape(label, resp):
    """An empty data layer yields an empty, well-formed envelope — not a crash
    and not a malformed shape. (Crash-freedom is asserted by the call site;
    here we assert the shape is the canonical empty one.)"""
    results = _get(resp, "results")
    total_matching = _get(resp, "total_matching")
    if results == [] and total_matching is not None:
        assert total_matching == 0, (
            f"{label}: empty results but total_matching={total_matching}"
        )
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/edge_cases/invariants.py
git commit -m "test(edge): defensive structural-invariant oracle"
```

### Task 2.2: Unit-test the oracle itself (no KG)

**Files:**
- Create: `tests/unit/test_edge_case_invariants.py`

- [ ] **Step 1: Write failing tests for the oracle using synthetic responses**

```python
import types
import pytest
from tests.integration.edge_cases import invariants as inv


def _resp(**kw):
    return types.SimpleNamespace(**kw)


class TestEnvelopeInvariants:
    def test_passes_on_consistent_empty(self):
        inv.assert_envelope_invariants(
            "t", _resp(results=[], total_matching=0, returned=0, truncated=False))

    def test_flags_returned_mismatch(self):
        with pytest.raises(AssertionError):
            inv.assert_envelope_invariants(
                "t", _resp(results=[1, 2], returned=3, truncated=False,
                           total_matching=3))

    def test_flags_negative_count(self):
        with pytest.raises(AssertionError):
            inv.assert_envelope_invariants("t", _resp(total_matching=-1))


class TestBatchDiagnostics:
    def test_not_found_subset_ok(self):
        inv.assert_batch_diagnostics(
            "t", _resp(not_found=["x"], not_matched=[]), input_ids=["x", "y"])

    def test_not_found_not_in_inputs_fails(self):
        with pytest.raises(AssertionError):
            inv.assert_batch_diagnostics(
                "t", _resp(not_found=["z"], not_matched=[]), input_ids=["x"])

    def test_structured_not_found_skipped(self):
        # Non-list not_found (structured submodel) is skipped, not crashed on.
        inv.assert_batch_diagnostics(
            "t", _resp(not_found=_resp(metabolite_ids=["z"]), not_matched=[]),
            input_ids=["x"])
```

- [ ] **Step 2: Run; verify the new tests pass (oracle already written)**

Run: `uv run pytest tests/unit/test_edge_case_invariants.py -v`
Expected: PASS. (Oracle exists from Task 2.1; these lock its behavior.)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_edge_case_invariants.py
git commit -m "test(edge): unit tests pinning the invariant oracle"
```

---

## Phase 3 — Matrix runner + representative tools

### Task 3.1: Runner infrastructure + scenario-builder pattern

**Files:**
- Create: `tests/integration/edge_cases/scenarios.py`
- Create: `tests/integration/test_edge_case_contracts.py`

- [ ] **Step 1: Define the scenario type and the per-tool scenario builders for 4 representative tools**

A `Scenario` is `(label, kwargs, expects_error, input_ids)`. `expects_error`
is `None` or the exception type the documented contract raises (e.g.
`ToolError` wrapping the multi-organism `ValueError`). `input_ids` feeds
`assert_batch_diagnostics` (empty when the tool has no batch id input).

Create `scenarios.py`:

```python
"""Per-tool degenerate-input scenarios for the corner-case matrix.

Each builder returns a list of Scenario tuples. A tool's baseline call is the
minimal valid invocation; each scenario substitutes ONE degenerate value.
"""
from dataclasses import dataclass, field
from fastmcp.exceptions import ToolError
from tests.integration.edge_cases import fixtures as fx


@dataclass
class Scenario:
    label: str
    kwargs: dict
    expects_error: type | None = None
    input_ids: list = field(default_factory=list)


def genes_by_ontology_scenarios():
    return [
        Scenario(
            "genome_only_organism",
            dict(ontology="cyanorak_role",
                 term_ids=["cyanorak.role:D.1.5"],
                 organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "expression_layer_empty_organism",
            dict(ontology="cyanorak_role",
                 term_ids=["cyanorak.role:D.1.5"],
                 organism=fx.EXPRESSION_LAYER_EMPTY_ORGANISM)),
        Scenario(
            "unknown_term",
            dict(ontology="go", term_ids=[fx.UNKNOWN_ONTOLOGY_TERM],
                 organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.UNKNOWN_ONTOLOGY_TERM]),
    ]


def gene_overview_scenarios():
    return [
        Scenario(
            "unknown_locus",
            dict(locus_tags=[fx.UNKNOWN_LOCUS], organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.UNKNOWN_LOCUS]),
        Scenario(
            "mixed_batch",
            dict(locus_tags=fx.MIXED_LOCUS_BATCH, organism=fx.CONTROL_ORGANISM),
            input_ids=fx.MIXED_LOCUS_BATCH),
        Scenario(
            "gene_no_de",
            dict(locus_tags=[fx.GENE_NO_DE], organism=fx.CONTROL_ORGANISM),
            input_ids=[fx.GENE_NO_DE]),
    ]


def differential_expression_by_gene_scenarios():
    return [
        Scenario(
            "genome_only_organism",
            dict(organism=fx.GENOME_ONLY_ORGANISM)),
        Scenario(
            "expression_layer_empty_organism",
            dict(organism=fx.EXPRESSION_LAYER_EMPTY_ORGANISM)),
        Scenario(
            "gene_no_de",
            dict(organism=fx.CONTROL_ORGANISM, locus_tags=[fx.GENE_NO_DE]),
            input_ids=[fx.GENE_NO_DE]),
        Scenario(
            "offset_past_end",
            dict(organism=fx.CONTROL_ORGANISM, offset=fx.OFFSET_PAST_END)),
    ]


def list_organisms_scenarios():
    return [
        Scenario(
            "unknown_organism_name",
            dict(organism_names=["Nonexistus fakeii"]),
            input_ids=["Nonexistus fakeii"]),
    ]


# Registry: tool name -> builder. Phase 4 fills the rest.
SCENARIO_BUILDERS = {
    "genes_by_ontology": genes_by_ontology_scenarios,
    "gene_overview": gene_overview_scenarios,
    "differential_expression_by_gene": differential_expression_by_gene_scenarios,
    "list_organisms": list_organisms_scenarios,
}
```

- [ ] **Step 2: Write the matrix runner**

Create `test_edge_case_contracts.py`. It imports the existing `tool_fns` and
`_ctx_with_conn` helpers from `test_mcp_tools.py` so it reuses the registered
wrapper layer.

```python
import pytest
from tests.integration.test_mcp_tools import tool_fns, _ctx_with_conn  # noqa: F401
from tests.integration.edge_cases import invariants as inv
from tests.integration.edge_cases.scenarios import SCENARIO_BUILDERS

_CASES = [
    (tool, sc)
    for tool, builder in SCENARIO_BUILDERS.items()
    for sc in builder()
]


@pytest.mark.kg
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,scenario",
    _CASES,
    ids=[f"{t}-{sc.label}" for t, sc in _CASES],
)
async def test_tool_edge_case_contract(tool_name, scenario, tool_fns, conn):
    ctx = _ctx_with_conn(conn)
    fn = tool_fns[tool_name]

    if scenario.expects_error is not None:
        with pytest.raises(scenario.expects_error):
            await fn(ctx, **scenario.kwargs)
        return

    # No documented error => must not raise (crash-freedom invariant).
    resp = await fn(ctx, **scenario.kwargs)

    label = f"{tool_name}:{scenario.label}"
    inv.assert_envelope_invariants(label, resp)
    inv.assert_empty_layer_shape(label, resp)
    if scenario.input_ids:
        inv.assert_batch_diagnostics(label, resp, scenario.input_ids)
```

- [ ] **Step 3: Run the representative matrix; triage failures**

Run: `uv run pytest tests/integration/test_edge_case_contracts.py -v -m kg`
Expected: most PASS. Any FAIL is either (a) a real bug — note it for Task 3.2,
or (b) a scenario that needs a documented `expects_error` (e.g. a required
param missing) — fix the scenario. Do NOT loosen an invariant to make a real
bug pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/edge_cases/scenarios.py tests/integration/test_edge_case_contracts.py
git commit -m "test(edge): matrix runner + scenarios for 4 representative tools"
```

### Task 3.2: Fix bugs surfaced by the representative matrix (repeat per bug)

**Files:**
- Modify: offending tool source
- Test: the tool's existing integration class (focused regression) + the matrix already covers it

- [ ] **Step 1: Confirm the failing matrix case reproduces the bug**

Run: `uv run pytest tests/integration/test_edge_case_contracts.py -k "<tool>-<label>" -v -m kg`
Expected: FAIL with the invariant violation / exception.

- [ ] **Step 2: Add a focused regression test in the tool's own class**

Mirror the matrix scenario as a named test in `test_mcp_tools.py` (so the bug
has a readable, permanent home independent of the matrix).

- [ ] **Step 3: Fix the source (empty-safe indexing / coalesce / correct empty envelope)**

Apply the minimal fix. Reuse the Phase-0 empty-safe pattern where it is the
same class.

- [ ] **Step 4: Run matrix case + focused test + the tool's full class**

Run: `uv run pytest tests/integration/ -k "<tool>" -v -m kg`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/ tests/integration/
git commit -m "fix(<tool>): <one-line description of corner-case fix>"
```

---

## Phase 4 — Extend to all tools + coverage gate

### Task 4.1: Coverage-gate meta-test

**Files:**
- Modify: `tests/integration/test_edge_case_contracts.py`

- [ ] **Step 1: Add a failing gate test asserting every registered tool has scenarios**

```python
from tests.unit.test_tool_wrappers import EXPECTED_TOOLS

# Tools with no meaningful degenerate input (pure schema/echo) may be exempted
# here, with a comment justifying each.
_EXEMPT = {
    "kg_schema",        # static schema dump, no entity input
    "kg_release_info",  # release identity, no entity input
    "run_cypher",       # raw escape hatch, arbitrary query
    "list_filter_values",  # static categorical lists
}


def test_every_tool_has_edge_scenarios():
    covered = set(SCENARIO_BUILDERS) | _EXEMPT
    missing = set(EXPECTED_TOOLS) - covered
    assert not missing, f"tools missing edge-case scenarios: {sorted(missing)}"
```

- [ ] **Step 2: Run; verify it fails listing the not-yet-covered tools**

Run: `uv run pytest tests/integration/test_edge_case_contracts.py::test_every_tool_has_edge_scenarios -v`
Expected: FAIL listing ~33 tools.

- [ ] **Step 3: Commit the gate (red)**

```bash
git add tests/integration/test_edge_case_contracts.py
git commit -m "test(edge): coverage gate — every tool needs edge scenarios"
```

### Task 4.2: Author scenarios for remaining tools (repeat until gate is green)

Work the gate's `missing` list down. For each tool, follow the **documented
pattern** from Task 3.1: write a `<tool>_scenarios()` builder and register it
in `SCENARIO_BUILDERS`. Pick scenarios from the axes that apply to that tool:

- **Single-organism genomic tools** (`gene_ontology_terms`,
  `gene_homologs`, `gene_aa_sequence`, `gene_neighbors`, `gene_details`,
  `gene_derived_metrics`, `gene_clusters_by_gene`, `gene_response_profile`,
  `genes_in_cluster`, `pathway_enrichment`, `cluster_enrichment`):
  genome-only organism, gene-with-no-layer, unknown locus, mixed batch.
- **Cross-organism / discovery tools** (`list_publications`,
  `list_experiments`, `list_clustering_analyses`, `list_derived_metrics`,
  `list_metabolites`, `list_metabolite_assays`, `search_ontology`,
  `search_homolog_groups`, `ontology_landscape`): unknown-id filter,
  offset-past-end, filter-empty combo.
- **Metabolite / assay drill-downs** (`genes_by_metabolite`,
  `metabolites_by_gene`, `genes_by_homolog_group`,
  `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`,
  `assays_by_metabolite`, `discussed_by_publication`,
  `differential_expression_by_ortholog`): unknown id, mixed batch,
  expression-layer-empty organism where organism-scoped.
- **Metric drill-downs** (`genes_by_numeric_metric`,
  `genes_by_boolean_metric`, `genes_by_categorical_metric`): rankable-gated /
  flag=False / unknown-category empty cases.
- **`resolve_gene`, `genes_by_function`:** unknown query, empty-result query.

For each tool:

- [ ] **Step 1: Determine the baseline valid call.** Find it from the tool's
  existing integration tests in `test_mcp_tools.py` or its about-content
  example (`multiomics_explorer/inputs/tools/<tool>.yaml`). Confirm the
  baseline passes before adding degenerate substitutions.

- [ ] **Step 2: Write the `<tool>_scenarios()` builder** in `scenarios.py`,
  substituting one degenerate fixture per scenario, setting `input_ids` for
  batch-id inputs and `expects_error=ToolError` for documented raises (e.g.
  cross-organism batches, all-unknown-locus where organism can't be inferred).

- [ ] **Step 3: Register it** in `SCENARIO_BUILDERS`.

- [ ] **Step 4: Run that tool's matrix slice.**

Run: `uv run pytest tests/integration/test_edge_case_contracts.py -k "<tool>-" -v -m kg`
Expected: PASS, or FAIL surfacing a real bug → handle via Task 3.2's loop.

- [ ] **Step 5: Commit.**

```bash
git add tests/integration/edge_cases/scenarios.py
git commit -m "test(edge): edge-case scenarios for <tool>"
```

- [ ] **Final step (after all tools): run the gate green**

Run: `uv run pytest tests/integration/test_edge_case_contracts.py::test_every_tool_has_edge_scenarios -v`
Expected: PASS (no missing tools).

---

## Phase 5 — Full-suite verification + finalize

### Task 5.1: Full matrix + regression run

- [ ] **Step 1: Run the entire edge-case matrix**

Run: `uv run pytest tests/integration/test_edge_case_contracts.py tests/integration/edge_cases/ -v -m kg`
Expected: PASS (all scenarios + guards).

- [ ] **Step 2: Run the full integration + regression suites for no regressions**

Run:
```bash
uv run pytest tests/unit/ -q
uv run pytest tests/integration/ -q -m kg
uv run pytest tests/regression/ -q -m kg
```
Expected: all green. If a regression golden legitimately changed, regenerate
with `uv run pytest tests/regression/ --force-regen -m kg` and review the diff.

### Task 5.2: Changelog + docs

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add a `### Added` entry**

```markdown
- Corner-case verification harness (`tests/integration/edge_cases/` +
  `test_edge_case_contracts.py`): every MCP tool is exercised against
  degenerate-but-valid inputs (genome-only / expression-empty organisms,
  missing & mixed batches, pagination/filter-empty boundaries, null props)
  and checked against structural invariants. A coverage gate fails if a
  registered tool has no edge-case scenarios.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): log corner-case verification harness"
```

### Task 5.3: Code review

- [ ] **Step 1: Run the repo code-review skill over the branch diff**

Invoke the `code-review` skill (per CLAUDE.md, after tool/behavior changes).
Address findings via the receiving-code-review skill.

- [ ] **Step 2: Finalize the branch** via the
  `superpowers:finishing-a-development-branch` skill (merge / PR decision).

---

## Self-review notes (filled by plan author)

- **Spec coverage:** all 4 axes have scenario sources (Task 3.1 + Task 4.2
  axis map); empty-layer + index-crash class covered by Phase 0 + Phase 3;
  self-validating bank = Task 1.2; invariant oracle = Phase 2; coverage gate =
  Task 4.1; one-time sweep widened to tools.py + analysis/*.py = Task 0.1.
- **Known deferrals:** generative fuzzing out of scope (spec YAGNI); per-tool
  scenario authoring in Phase 4 is mechanical and gated by Task 4.1 rather
  than spelled out 41× (each follows the Task 3.1 pattern with a discovered
  baseline call).
- **Type consistency:** `Scenario` fields (`label/kwargs/expects_error/
  input_ids`) used identically in scenarios.py and the runner; oracle fn names
  (`assert_envelope_invariants`, `assert_batch_diagnostics`,
  `assert_empty_layer_shape`) consistent between definition and call sites.
