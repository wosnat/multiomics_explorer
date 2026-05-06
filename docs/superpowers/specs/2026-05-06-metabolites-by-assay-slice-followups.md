# Explorer-side follow-up backlog: metabolites-by-assay slice

**Date:** 2026-05-06
**Driver:** `/layer-rules` + `/add-or-update-tool` post-merge review of [docs/superpowers/plans/2026-05-06-metabolites-by-assay-slice.md](../plans/2026-05-06-metabolites-by-assay-slice.md) (merged at `1b93c54` on main).
**Slice commits:** `5efd1e6` → `a5a858d` (8 commits) + `1b93c54` (plan-doc record).
**Status:** all items are non-blocking — slice shipped APPROVED with these as low-priority cleanup. None blocks production use of the 3 new tools.
**Audience:** explorer maintainers (NOT KG team — for KG-side asks see [docs/kg-specs/2026-05-06-metabolites-followup-asks.md](../../kg-specs/2026-05-06-metabolites-followup-asks.md)).

---

## 1. Why this doc

`/layer-rules` and `/add-or-update-tool` reviews surfaced 5 explorer-side cleanups + 1 meta-recommendation to the orchestrating skill. All are post-merge polish that the code-reviewer judged acceptable to ship as-is. Filing them here so they don't fall through the cracks; pick up opportunistically.

## 2. Item summary table

| ID | Layer | Pri | Effort | Surface |
|---|---|---|---|---|
| EX-MET-01 | L1 (queries_lib) | P3 | XS | Drop dead `rel_alias` param in `_assays_by_metabolite_branch_conditions` (or actually use it for edge-side filters) |
| EX-MET-02 | L1 (queries_lib) | P3 | S | Replace `WHERE false` zero-row guard in `build_assays_by_metabolite[_summary]` with simpler branch omission once test guard is relaxed |
| EX-MET-03 | L3 (mcp_server) | P3 | M | Cross-tool wrapper-idiom cleanup: replace per-rollup manual instantiation with single `Response(**data)` (project-wide drift, not slice-scoped) |
| EX-MET-04 | L2 (api/) | P2 | XS | Add 1-line `assay_ids` existence probe in `metabolites_by_flags_assay()` so structured `not_found.assay_ids` is populated |
| EX-MET-05 | L2 (api/) | P2 | S | Compute `metabolites_with_evidence`/`without_evidence` partition in `assays_by_metabolite()` summary mode (currently empty per `gene_derived_metrics` precedent) |
| AOUT-01 | meta (skill) | P3 | XS | Document the dataflow-dependency caveat in `add-or-update-tool/SKILL.md` Stage 2 GREEN parallel-dispatch claim |

Pri scale: P0 (blocker) … P3 (nice-to-have). All P2/P3 here.

---

## 3. Per-item detail

### EX-MET-01 — Dead `rel_alias` param in `_assays_by_metabolite_branch_conditions` (P3 / XS)

**File:** [`multiomics_explorer/kg/queries_lib.py`](../../../multiomics_explorer/kg/queries_lib.py) lines 8319-8348.

**Observation:** The helper's signature accepts `rel_alias: str  # 'rq' or 'rf'` but the body never references it. All conditions emitted (`a.organism_name`, `m.id`, `a.metric_type`, `a.compartment`) are node-side, never edge-side, so the rel-alias is irrelevant. The param is forward-compat for edge-side filters (e.g. `rq.value >= ...`) that don't yet exist.

**Resolution paths (pick one):**
- (a) Drop the param. Simpler. If edge-side filters are added later, reintroduce.
- (b) Add an edge-side filter that uses it (e.g. `rq.value`-anchored — but those would diverge across branches, breaking the shared-WHERE-block model).

**Recommendation:** (a). YAGNI. The current helper signature implies branch-divergence that doesn't exist; remove until needed.

---

### EX-MET-02 — `WHERE false` zero-row guard in `assays_by_metabolite` (P3 / S)

**File:** [`multiomics_explorer/kg/queries_lib.py`](../../../multiomics_explorer/kg/queries_lib.py) lines 8568-8590 (detail builder); equivalent block in summary builder.

**Observation:** When `evidence_kind` filters one arm out, the production builder does NOT omit that arm's `MATCH` clause. Instead it rewrites the WHERE to `WHERE false AND m.id IN $metabolite_ids`, keeping the dead `rq` / `rf` rel-alias in the cypher text so the test invariant `assert "[rq:Assay_quantifies_metabolite]" in cypher AND "[rf:Assay_flags_metabolite]" in cypher` continues to pass.

The comment at line 8568-8569 acknowledges this:
> `# Both rel-aliases must appear in cypher text for anti-pattern guards in tests, even when evidence_kind filters one branch out.`

**Why it's a smell:** code shape driven by test invariants, where the test invariant is over-tight (the anti-pattern guard's *real* job is to flag `[r:Assay_quantifies_metabolite|Assay_flags_metabolite]` polymorphic merges; it conflated that with rel-alias presence).

**Resolution path:**
1. Relax `TestBuildAssaysByMetabolite::test_union_all_skeleton` and `TestBuildAssaysByMetaboliteSummary::test_union_all_with_distinct_rel_vars` to assert presence of both rel-aliases **only when `evidence_kind is None`**.
2. Drop the `WHERE false` zero-row pattern; emit only the active arm when `evidence_kind` is set.
3. Re-verify via CyVer + integration tests (the `evidence_kind='quantifies'` / `'flags'` integration-test paths cover this).

Net: cleaner Cypher, simpler builder, anti-pattern guard still enforced where it matters.

---

### EX-MET-03 — Cross-tool wrapper-idiom drift: per-rollup manual instantiation (P3 / M)

**File:** [`multiomics_explorer/mcp_server/tools.py`](../../../multiomics_explorer/mcp_server/tools.py) — sampled in this slice at lines 8716-8746 (`metabolites_by_quantifies_assay`), 9020-9050 (`metabolites_by_flags_assay`), 9320-9360 (`assays_by_metabolite`).

**Observation:** `/layer-rules` skill prescribes `Response(**data)` for thin Layer-3 validation. Pydantic v2 nested-model coercion would do all per-rollup instantiation automatically. The current shape across these wrappers (and earlier same-day Tool 1 `list_metabolite_assays`, plus several other recent wrappers) is:

```python
# Current — verbose, requires wrapper edit when api/ adds an envelope key
results = [MetabolitesByQuantifiesAssayResult(**r) for r in data["results"]]
by_detection_status = [MqaByDetectionStatus(**b) for b in data["by_detection_status"]]
# ... 6 more rollups, each manually iterated ...
return MetabolitesByQuantifiesAssayResponse(results=results, by_detection_status=..., ...)
```

vs. the layer-rules canonical:

```python
# Canonical — thin, auto-coerces nested models, picks up new envelope keys for free
return MetabolitesByQuantifiesAssayResponse(**data)
```

**Why it's a project-wide drift, not slice-scoped:** the new slice's wrappers consistently follow the **already-shipped** verbose idiom (Tool 1 `list_metabolite_assays`, plus older `genes_by_*`, `gene_*` wrappers). Rewriting just the slice's 3 wrappers would create inconsistency.

**Resolution path:**
1. Audit how many existing wrappers use the verbose idiom (likely ~20+).
2. Sweep refactor: replace per-rollup manual instantiation with `Response(**data)` across all wrappers.
3. Verify no behavior change via the existing test suite (Pydantic auto-coercion produces equivalent objects).
4. If any wrapper has *legitimate* per-rollup transform logic (e.g. computed fields, ToolError on rollup-specific bad shape), keep that case verbose with a comment.

**Effort:** M (medium) — touches all wrappers, but mechanical. One PR of pure refactor.

---

### EX-MET-04 — `metabolites_by_flags_assay` skips `assay_ids` existence probe (P2 / XS)

**File:** [`multiomics_explorer/api/functions.py`](../../../multiomics_explorer/api/functions.py) lines 6558-6565 (the inline comment flagging this).

**Observation:** When unknown `assay_ids` are passed, `not_found.assay_ids` returns `[]` instead of the missing IDs. The structured envelope shape is preserved (`not_found` is the 4-key `MfaNotFound` model per parent §13.6); only this one bucket is best-effort.

The deviation arose from: parent §13.6 requires structured `not_found` for multi-batch tools; the boolean tool has no `_diagnostics` builder (parent §13.1 explicitly skips it: "boolean DM precedent shows the `flag_value` filter has no gate to probe"); a Task 1 RED test (`TestMetabolitesByFlagsAssay::test_no_rankable_diagnostics`) pinned a strict 2-query dispatch (summary + detail).

**Resolution path:** add a 1-Cypher existence probe that's not framed as "diagnostics":

```python
# In metabolites_by_flags_assay():
probe_cypher = "MATCH (a:MetaboliteAssay) WHERE a.id IN $assay_ids RETURN a.id"
present_ids = {r["a.id"] for r in conn.execute_query(probe_cypher, assay_ids=assay_ids)}
not_found_assay_ids = sorted(set(assay_ids) - present_ids)
```

Cost: 1 extra Cypher round-trip on a small list — negligible. The pinned test counts a different surface ("rankable diagnostics aren't called"); existence probe doesn't violate that.

**Test impact:** add a new test `test_assay_ids_existence_probe_populates_not_found` that asserts unknown IDs surface in `not_found.assay_ids`. Update the inline TODO comment in the api/ function. Possibly delete `test_assay_ids_not_found_task3_deviation` (the integration test that pins current empty behavior — it would become obsolete).

---

### EX-MET-05 — `assays_by_metabolite` summary-mode partition empty (P2 / S)

**File:** [`multiomics_explorer/api/functions.py`](../../../multiomics_explorer/api/functions.py) lines 6719-6735 (the inline comment).

**Observation:** In `summary=True` mode, `metabolites_with_evidence=[]` and `metabolites_without_evidence` includes every input metabolite_id — because the partition is currently computed from `results` rows (which is `[]` in summary mode).

**Why it's acceptable today:** `gene_derived_metrics` has the same shape with the same precedent. Slice spec §6.3 explicitly mirrors that pattern.

**Why it should still be fixed:** the partition is *useful* in summary mode (50+ metabolite_id batch routing was the original use case for `summary=True`). Without it, callers can't tell from the summary which inputs hit anything.

**Resolution path:** extend the summary builder to project distinct `metabolite_id`s seen across both UNION ALL branches, and compute the partition from that.

```cypher
// Add to build_assays_by_metabolite_summary, alongside the existing rollups:
WITH ..., apoc.coll.toSet([m_id IN m_ids WHERE m_id IS NOT NULL]) AS metabolites_with_evidence_ids
RETURN ..., metabolites_with_evidence_ids
```

Then api/ partitions:

```python
with_evidence = sorted(env.get("metabolites_with_evidence_ids", []))
without_evidence = sorted(set(metabolite_ids) - set(with_evidence))
```

Update the integration test `test_metabolites_with_evidence_partition_detail_mode` to also cover summary mode.

**Effort:** S — single Cypher line added + small api/ change + 1 test extension.

---

### AOUT-01 — `add-or-update-tool` Stage 2 parallel-dispatch caveat (P3 / XS)

**File:** [`.claude/skills/add-or-update-tool/SKILL.md`](../../../.claude/skills/add-or-update-tool/SKILL.md) Stage 2 — GREEN section.

**Observation:** The skill currently states:

> Dispatch the 4 implementer agents in **one** message, in parallel. Each owns a different file → collision-safe by construction.

Empirically, the 4 implementers are NOT independently parallel-safe in this codebase. Each agent's scoped self-verify (`pytest tests/unit/test_<layer>.py`) imports the prior layer's outputs:

- `test_api_functions.py` imports `metabolites_by_quantifies_assay` from `api.functions`, which imports `build_metabolites_by_quantifies_assay` from `kg.queries_lib`.
- `test_tool_wrappers.py` imports the wrapper, which imports the api/ function.
- `build_about_content.py` introspects `mcp_server.tools` Pydantic models.

If `query-builder` hasn't committed when `api-updater` runs, `api-updater`'s scoped self-verify fails at import time, not at logic. Same chain for `tool-wrapper` (depends on api/ exports) and `doc-updater` (depends on tools.py Pydantic models).

The slice shipped because the implementer agents were dispatched **sequentially** instead, contra the skill's prescribed parallel pattern. The collision-safety claim addresses *file collision* (no two agents touch the same file), not *dataflow collision*.

**Resolution path:** clarify Stage 2 wording to acknowledge two parallelism modes:

```diff
- Dispatch the 4 implementer agents in **one** message, in parallel. Each
- owns a different file → collision-safe by construction.
+ Dispatch the 4 implementer agents. Each owns a different file → file-
+ collision-safe by construction. Whether they run in parallel depends on
+ the codebase's dataflow shape:
+
+ - **Parallel** is safe when each layer's tests can self-verify without
+   importing later layers' outputs (e.g. when the test suite stubs
+   cross-layer dependencies).
+ - **Sequential** (queries → api → tools → docs) is required when
+   `test_<layer>.py` imports prior layers' real implementations and
+   self-verifies at GREEN — the case in this codebase. In sequential
+   mode, dispatch each agent only after the prior one commits; the
+   layer-cut still enforces zero file collisions.
+
+ Either way, the orchestrator pytest at Stage 3 is the integration gate.
```

**Why it matters:** future builds that follow this skill literally will hit the same impedance and either (a) discover sequential dispatch is needed mid-stream (wasted time), or (b) bypass the GREEN scoped self-verify entirely (loses the test-driven discipline the skill was designed to enforce).

---

## 4. Sequencing recommendation

If a maintainer picks this backlog up:

1. **EX-MET-04** first (XS, P2) — populates structured `not_found` correctly. Smallest user-facing improvement.
2. **EX-MET-05** next (S, P2) — summary-mode partition computation. Makes batch routing actually work in summary mode.
3. **AOUT-01** in parallel (XS, P3) — pure docs to `add-or-update-tool` SKILL.md. No code impact.
4. **EX-MET-01** + **EX-MET-02** as a pair (XS+S, P3) — Cypher cleanup + test-guard relaxation. Good "afternoon refactor" combo.
5. **EX-MET-03** last (M, P3) — cross-tool wrapper-idiom sweep. Touches many files; do alone in its own PR.

Each is independent; pick any order.

## 5. References

- Plan: [docs/superpowers/plans/2026-05-06-metabolites-by-assay-slice.md](../plans/2026-05-06-metabolites-by-assay-slice.md)
- Slice spec: [docs/tool-specs/metabolites_by_assay.md](../../tool-specs/metabolites_by_assay.md)
- Parent spec: [docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md](../../tool-specs/2026-05-05-phase5-greenfield-assay-tools.md)
- Layer-rules skill: `.claude/skills/layer-rules/SKILL.md`
- Add-or-update-tool skill: `.claude/skills/add-or-update-tool/SKILL.md`
- KG-side asks (separate doc, KG team audience): [docs/kg-specs/2026-05-06-metabolites-followup-asks.md](../../kg-specs/2026-05-06-metabolites-followup-asks.md)
