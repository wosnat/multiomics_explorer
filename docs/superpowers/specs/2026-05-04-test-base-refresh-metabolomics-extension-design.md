# Test-base refresh: metabolomics-extension KG

**Status:** design
**Date:** 2026-05-04
**Trigger:** New KG built with metabolomics-extension (Capovilla 2023 + Kujawinski 2023 papers ingested via the new `MetaboliteAssay` adapter — see [metabolomics-extension.md](../../../../multiomics_biocypher_kg/docs/kg-changes/metabolomics-extension.md))
**Scope posture:** B — refresh tests + add guard rails. **Tools, queries, API, wrappers untouched.** Surfacing new metabolomics fields in tool outputs is deferred to separate specs.
**Done bar:** B — full test suite green + per-tool change report classifying every failure and every baseline diff.

## 1. Context

The new KG is loaded at `bolt://localhost:7687` and verified via `scripts/validate_connection.py`. It introduces:

**New entities (additive):**
- Node label `MetaboliteAssay` (10 nodes in current build)
- Edge types `Assay_quantifies_metabolite`, `Assay_flags_metabolite`
- Binding edges `PublicationHasMetaboliteAssay`, `ExperimentHasMetaboliteAssay`, `MetaboliteAssayBelongsToOrganism`
- Compartment `extracellular` (added to `COMPARTMENTS` frozenset)
- Organism `MIT0801` (Prochlorococcus, LLI ecotype) registered with validator

**Property additions on existing types:**
- `Metabolite`: `evidence_sources` extended with `"metabolomics"`; new fields `measured_assay_count`, `measured_organisms`, `measured_paper_count`, `organism_count`, `organism_names`
- `Organism_has_metabolite`: `evidence_sources` extended with `"measured"`; new fields `measured_assay_count`, `measured_compartments`, `measured_paper_count`
- `Experiment`, `Publication`: `metabolite_assay_count`, `metabolite_compartments`, `metabolite_count`
- `OrganismTaxon`: `measured_metabolite_count`

**Behavioral change (non-additive):**
- `Organism_has_metabolite` materialization now creates an edge whenever any `MetaboliteAssay` quantifies/flags a metabolite for the organism — even with no gene-catalysis or gene-transport path. **This expands row counts in any query traversing `Organism_has_metabolite`** (notably `genes_by_metabolite`, `metabolites_by_gene`).

## 2. Why this matters for tests

The current tool surface (designed before metabolomics-extension landed) does not expose any of the new fields, so a pure additive change in nodes/properties wouldn't normally affect tool outputs. But:

- **149 regression YAMLs** capture envelope rollups like `top_organisms`, `top_metabolites`, `by_evidence_source`, `compartments_observed`, `by_organism`. Every rollup that reads from `Metabolite`, `Organism_has_metabolite`, `Experiment`, `Publication`, or `OrganismTaxon` is a candidate for drift.
- The `Organism_has_metabolite` materialization expansion is a **semantic change**, not just data drift. Any `genes_by_metabolite` / `metabolites_by_gene` baseline that previously had N rows for an organism with paper measurements now has more — the tool returns rows for organism-metabolite pairs that have *only* a measurement-path edge, even though the gene has no chemical relationship to the metabolite.
- `tests/integration/test_kg_constants_drift.py` will fail by design — it asserts the schema is what it was, and now it isn't.

## 3. Risk: blind `--force-regen` is the wrong move

A naive "regen all baselines and call it green" silently absorbs:
- Real bugs introduced by KG-side adapter changes
- Materialization expansion that should be acknowledged explicitly (not buried in a 149-file diff)
- Future schema regressions to the old rules (no test catches them)

The design defends against this with **sequential layer-by-layer triage** + a **classification rubric** + **positive guard-rail tests** that pin the new behaviors.

## 4. Process flow

Phases run strictly in order. Each phase classifies its failures before moving to the next; the regen step (phase 6) runs only after phases 1–5 are zero-failure.

| Phase | Command | Purpose | Action |
|---|---|---|---|
| 0 | `pytest tests/ 2>&1 \| tee /tmp/refresh-baseline.log` | Snapshot the unfiltered failure surface | Capture only — do not fix |
| 1 | `pytest tests/integration/test_kg_constants_drift.py -m kg` | Surface schema delta | Hand-update the constants asserted by this test to match the metabolomics-extension doc **exactly**. Reject any constant that's not documented. Out of scope: query-builder code in `kg/queries_lib.py`. In scope only if a non-builder schema literal in `kg/queries.py` (e.g., the few-shot examples block or a hardcoded label list referenced *only by tests*) needs syncing — and only as a constant edit, never a query change. |
| 2 | `pytest tests/unit/ -v` | Pure code logic — should be data-independent | If any fail: legit bug. Stop and surface before continuing. |
| 3 | `pytest tests/integration/test_cyver_queries.py -m kg` | All builders validate against new schema | Add new map projection keys (`measured_assay_count`, `metabolite_count`, `metabolite_compartments`, etc.) to `_KNOWN_MAP_KEYS` only if a builder *already* projects them. Builder-internal errors → out of scope, file follow-up. |
| 4 | `pytest tests/integration/test_tool_correctness_kg.py tests/integration/test_mcp_tools.py tests/integration/test_api_contract.py tests/integration/test_about_examples.py tests/integration/test_param_edge_cases.py tests/integration/test_examples.py tests/integration/test_analysis.py` | Hardcoded counts and IDs in assertions | For each failure, **prefer rebinding** to a stable reference (e.g., assert a known gene like `PMM1714` is in the result, or assert organism `prochlorococcus_med4` appears in `by_organism`) over loosening to `>=`. Loosen only when no stable reference applies. **Document every change in the report.** |
| 5 | `pytest tests/evals/test_eval.py` | `cases.yaml` hardcoded `row0` / `contains` / `columns` | Edit YAML; document. |
| 6 | `pytest tests/regression/ -m kg --force-regen` then `git diff tests/regression/test_regression/` | Bulk baseline refresh | **Triage every diff per the rubric in §5.** Classify before commit. |
| 7 | New test file (see §6) | Pin new behaviors as positive invariants | Add 3 guard-rail tests. |
| 8 | `pytest tests/ -v` | Reproducibility check | All green or stop. |

## 5. Diff classification rubric (phase 6)

Every regression diff is assigned **one or more** classes from the set below. A baseline that gained both new organisms and new compartments is `new_organism + new_compartment` — both stay in the report.

| Class | Cause | Acceptable without escalation? |
|---|---|---|
| `data_drift` | New publications / genes / metabolites loaded — counts grew | Yes if delta proportional to documented additions |
| `materialization_expansion` | `Organism_has_metabolite` measurement-only path adds rows in `genes_by_metabolite` / `metabolites_by_gene` | Yes — documented extension |
| `new_compartment` | `extracellular` appears in `compartments_observed` / `by_compartment` rollups | Yes |
| `new_organism` | `MIT0801` appears in `by_organism` / `top_organisms` rollups | Yes |
| `evidence_source_extension` | `evidence_sources` arrays contain `"metabolomics"` or `"measured"` | Yes |
| `unclassified` | Doesn't fit above | **No — investigate. Do not commit until classified.** |

**Process:** for each baseline with a non-empty diff, the report records: filename, row-count delta, top-fields-changed, class set, one-line reason.

A baseline whose diff cannot be fully explained by the acceptable classes is `unclassified` (even if it *also* matches an acceptable class) — escalated, not absorbed.

## 6. Guard-rail tests (phase 7)

New file: **`tests/integration/test_metabolomics_extension_invariants.py`**.

Three positive Cypher assertions, each ~10 lines. Each pins one *new* behavior so a future regression to the old schema/materialization breaks tests instead of silently changing baselines.

```python
@pytest.mark.kg
def test_metabolite_assay_nodes_present(conn):
    """Pins the new MetaboliteAssay node type as a populated KG entity."""
    rows = conn.execute_query("MATCH (m:MetaboliteAssay) RETURN count(m) AS n")
    assert rows[0]["n"] > 0

@pytest.mark.kg
def test_organism_has_metabolite_measured_path_materialized(conn):
    """Pins the documented expansion of Organism_has_metabolite to the measurement-only path."""
    rows = conn.execute_query(
        "MATCH ()-[r:Organism_has_metabolite]-() "
        "WHERE 'measured' IN coalesce(r.evidence_sources, []) "
        "RETURN count(r) AS n"
    )
    assert rows[0]["n"] > 0

@pytest.mark.kg
def test_metabolite_metabolomics_evidence_tag_present(conn):
    """Pins the metabolomics evidence_sources tagging on Metabolite nodes."""
    rows = conn.execute_query(
        "MATCH (m:Metabolite) "
        "WHERE 'metabolomics' IN coalesce(m.evidence_sources, []) "
        "RETURN count(m) AS n"
    )
    assert rows[0]["n"] > 0
```

These three assertions are deliberately minimal — they don't pin counts (which would just become more drift surface), only the binary "the new thing is loaded".

## 7. Change report

Path: **`docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md`** (sibling to this design).

Structure:

```markdown
# Test-base refresh report — metabolomics-extension

## Phase 0: Baseline failure surface
[count of failures by test file, raw]

## Phase 1: Schema drift
- Failures: [list]
- Updates applied: [filename → what changed → why]

## Phase 2: Unit tests
- Failures: [list — should be empty]

## Phase 3: CyVer
- Failures: [list]
- Updates applied: [list]

## Phase 4: Integration correctness
[per-failure: file:test_name | failure mode | fix | reason class]

## Phase 5: Eval cases
[per-case in cases.yaml: case_id | failure | fix]

## Phase 6: Regression baselines (149 YAMLs)

### Summary
- Unchanged: N
- Changed: N
- Classified breakdown: [counts per class]

### Per-baseline detail
| Baseline | Δ rows | Fields changed | Class | Reason |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

### Unclassified diffs
[list — escalated, not absorbed]

## Phase 7: Guard rails added
- [3 new assertions, link to test file]

## Phase 8: Final verification
- pytest tests/ : all green
- Time: [duration]

## Open follow-ups (out of scope)
- Surface new metabolomics fields in tool outputs
- ...
```

## 8. Out of scope (explicit)

- ❌ Changes to `multiomics_explorer/mcp_server/tools.py`
- ❌ Changes to `multiomics_explorer/kg/queries_lib.py`
- ❌ Changes to `multiomics_explorer/api/functions.py`
- ❌ Surfacing `evidence_sources='measured'` filters or `measured_*` envelope rollups
- ❌ New tool examples in `inputs/tools/*.yaml` (only fix existing example assertions if they break)
- ❌ Sentinel biological-truth assertions (separate effort)
- ❌ Pinning `Organism_has_metabolite` semantics to old rule via query filter (would be a tool change)

## 9. Deliverables

1. Updated tests across phases 1–5 (assertions, fixtures, eval cases)
2. Refreshed regression baselines (`tests/regression/test_regression/*.yml`) with classified diffs
3. New file: `tests/integration/test_metabolomics_extension_invariants.py` (3 guard rails)
4. Change report: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md`
5. `pytest tests/ -v` all green

## 10. Branch posture

- Direct branch off main: `refresh/test-base-metabolomics-extension`
- No worktree — tests-only, sequential phases, no parallel agents
- Single commit per phase preferred (so the change-report classification can reference commits) — but flexible if a phase produces no changes

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Mass regen absorbs a real bug | Sequential phases — regen runs last, after all non-regen failures classified |
| Materialization expansion buried in 149-file diff | Diff classification rubric forces explicit acknowledgment; guard rail makes it a positive invariant |
| Schema additions go unnoticed in `kg/queries.py` literals | Phase 1 is gated on the constants drift test, which exhaustively asserts the schema |
| A test that fails for a reason not captured by the rubric is forced into a category | `unclassified` is a first-class category — escalation, not absorption |
| Phase 4 loosening weakens a test | Phase 4 explicitly *prefers* rebinding to stable references; loosening to `>=` is fallback only. Every loosening is documented in the report so reviewers can challenge it. |
