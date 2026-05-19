# Phase 3 — Compound-anchored tightening + ergonomics — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sharpen the row schema and docstrings on the compound-anchored chemistry tools (`genes_by_metabolite`, `metabolites_by_gene`, `list_metabolites`) so consumers read consistent shapes and accurate "involved in" / reversibility framing — plus rewrite the family_inferred-dominance warning and disambiguate the `by_element` / `elements` semantics.

**Architecture:** Five small items across three layers. Two code edits (sparse-field tuple reduction, two warning string rewrites) + four docstring/about-content edits + one analysis-doc one-liner. No KG iteration; no Cypher changes. TDD where there is testable behavior; manual visual verification for docstrings.

**Tech Stack:** Python 3.13, Pydantic, FastMCP, Neo4j (read-only), pytest (`pytest -m kg` for KG-integration), uv (package manager).

**Spec:** [docs/tool-specs/2026-05-05-phase3-compound-anchored-tightening.md](../../tool-specs/2026-05-05-phase3-compound-anchored-tightening.md)
**Roadmap:** [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md](../specs/2026-05-05-metabolites-surface-refresh-roadmap.md) — Phase 3
**Predecessors:** Phase 1 + Phase 2 both landed on main 2026-05-05 (Phase 2 fast-forward `12c7068..d99784a`).
**Item 5 (`query=` alias) — DROPPED 2026-05-06**, do NOT touch any list/search-tool kwarg signature.
**Item 6.3 precision_tier scenario removal — already complete** (verified 2026-05-06: `examples/metabolites.py` no longer carries it; only verification step remains).

---

## File Structure

| File | Responsibility | Items |
|---|---|---|
| `multiomics_explorer/api/functions.py` | Reduce `_GBM_SPARSE_FIELDS` tuple; rewrite the two family_inferred-dominance warning strings (GBM + MBG) | 6.1, 6.3 |
| `multiomics_explorer/mcp_server/tools.py` | Update Pydantic class docstrings + per-field descriptions for `GeneReactionMetaboliteTriplet`, `MbgByElement`, `MetabolitesByGeneResponse.by_element`, list_metabolites row `elements`. Update MCP tool docstrings for GBM, MBG, list_metabolites. | 6.1, 6.2, 6.4 |
| `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` | Track A1 reversibility extension; one-line `chem["top_genes"]` → `chem["by_gene"]` correction at line 216; verify no `precision_tier` reference remains | 6.2, 6.6 |
| `multiomics_explorer/inputs/tools/{genes_by_metabolite,metabolites_by_gene,list_metabolites}.yaml` | About-content mistake entries + example response updates | 6.1, 6.2, 6.3, 6.4 |
| `tests/unit/test_api_functions.py` | New TDD tests for None-padding (per arm) + warning rewrite (per tool); update existing tests that asserted "key absent" on cross-arm fields | 6.1, 6.3 |
| `tests/unit/test_tool_wrappers.py` | New TDD test for envelope-side serialization preserving None values on cross-arm fields | 6.1 |
| `tests/regression/` | `--force-regen` for GBM + MBG fixtures (rows now wider) + new warning text | 6.1, 6.3 |
| `CLAUDE.md` | Tool-table prose touch-ups for the 3 affected tools where row prose mentions warning text, row shape, or element semantics | 6.1, 6.3, 6.4 |

---

## Pre-flight

### Task 0: Verify worktree + predecessor state

**Files:** none — read-only verification.

- [ ] **Step 1: Confirm Phase 1 + Phase 2 are still on main**

Run:
```bash
git log --oneline main | head -20
```
Expected: top commits include the Phase 2 merge (commits in range `12c7068..d99784a`); the spec was frozen at this state. If either Phase 1 or Phase 2 has been reverted or force-pushed off, halt and ask for guidance.

- [ ] **Step 2: Confirm worktree branch matches main HEAD**

Run:
```bash
git status
git log --oneline -1
```
Expected: clean working tree on the Phase 3 worktree branch; HEAD matches main (or 1 commit ahead with the worktree-init commit).

- [ ] **Step 3: Locate code anchors via grep (not line numbers)**

Run all four greps to confirm anchor presence (line numbers will have shifted from spec — anchors are stable):
```bash
grep -n "^_GBM_SPARSE_FIELDS\|^_MBG_SPARSE_FIELDS" multiomics_explorer/api/functions.py
grep -n "Majority of transport rows are family_inferred\|Transport rows in this slice are dominated" multiomics_explorer/api/functions.py
grep -n "class GeneReactionMetaboliteTriplet\|class MbgByElement\|class MetabolitesByGeneResponse" multiomics_explorer/mcp_server/tools.py
grep -n 'chem\["top_genes"\]' multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
```
Expected: all four anchors found. Note the current line numbers (used as starting points; greps run again at edit time).

---

## Item 1 — None-padding for cross-arm fields (GBM + MBG)

### Task 1: Write failing API tests for None-padding (TDD red)

**Files:**
- Modify: `tests/unit/test_api_functions.py` (add tests inside `class TestGenesByMetabolite` and `class TestMetabolitesByGene`)

**Cross-arm fields:** `transport_confidence`, `tcdb_family_id`, `tcdb_family_name` (transport-only — None on metabolism rows); `reaction_id`, `reaction_name`, `ec_numbers`, `mass_balance` (metabolism-only — None on transport rows).

- [ ] **Step 1: Add `test_cross_arm_fields_none_padded` to TestGenesByMetabolite**

Locate `class TestGenesByMetabolite` via `grep -n "^class TestGenesByMetabolite" tests/unit/test_api_functions.py`. Add a new test method inside the class (immediately after an existing test for shape consistency):

```python
def test_cross_arm_fields_none_padded(self, mock_conn_with_mixed_arm_rows):
    """After Item 6.1 None-padding: every result row carries all 7 cross-arm
    keys; arm-specific fields are explicitly None on rows from the other arm.
    """
    out = api.genes_by_metabolite(
        metabolite_ids=["kegg.compound:C00086"],
        organism="Prochlorococcus marinus MED4",
        conn=mock_conn_with_mixed_arm_rows,
    )

    # Find one metabolism row and one transport row in results
    metabolism_rows = [r for r in out["results"] if r["evidence_source"] == "metabolism"]
    transport_rows = [r for r in out["results"] if r["evidence_source"] == "transport"]
    assert metabolism_rows, "fixture must include at least one metabolism row"
    assert transport_rows, "fixture must include at least one transport row"

    # Metabolism rows: transport-arm cross-arm keys present, value None
    for row in metabolism_rows:
        assert "transport_confidence" in row
        assert row["transport_confidence"] is None
        assert "tcdb_family_id" in row
        assert row["tcdb_family_id"] is None
        assert "tcdb_family_name" in row
        assert row["tcdb_family_name"] is None

    # Transport rows: metabolism-arm cross-arm keys present, value None
    for row in transport_rows:
        assert "reaction_id" in row
        assert row["reaction_id"] is None
        assert "reaction_name" in row
        assert row["reaction_name"] is None
        assert "ec_numbers" in row
        assert row["ec_numbers"] is None
        assert "mass_balance" in row
        assert row["mass_balance"] is None
```

If a fixture `mock_conn_with_mixed_arm_rows` doesn't exist, reuse the existing conn fixture from the existing GBM test class (e.g., the one used by `test_family_inferred_dominance_warning_fires` at the existing site). Confirm the mock raw-row data already includes None values for cross-arm fields on the appropriate arm — current fixtures do (verified 2026-05-06).

- [ ] **Step 2: Add the same test to TestMetabolitesByGene**

Add a structurally identical test method inside `class TestMetabolitesByGene` (locate via grep). The test body is identical except for the `api.metabolites_by_gene(locus_tags=["PMM0001"], organism="Prochlorococcus marinus MED4", ...)` call instead of `api.genes_by_metabolite(...)`. Pick fixture inputs that produce both metabolism and transport rows (PMM0001 has metabolism; choose a mixed-arm gene from the existing test fixtures).

- [ ] **Step 3: Run the new tests and confirm they FAIL**

Run:
```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite::test_cross_arm_fields_none_padded tests/unit/test_api_functions.py::TestMetabolitesByGene::test_cross_arm_fields_none_padded -v
```
Expected: both tests FAIL with `AssertionError: assert "transport_confidence" in row` (or similar key-absent failure) — because the current `_GBM_SPARSE_FIELDS` strips these keys when None.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/unit/test_api_functions.py
git commit -m "test: add failing tests for None-padding on cross-arm fields (Item 6.1, TDD red)"
```

---

### Task 2: Implement None-padding (TDD green)

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `_GBM_SPARSE_FIELDS` tuple definition

- [ ] **Step 1: Locate `_GBM_SPARSE_FIELDS` and `_MBG_SPARSE_FIELDS`**

Run:
```bash
grep -n "^_GBM_SPARSE_FIELDS\|^_MBG_SPARSE_FIELDS" multiomics_explorer/api/functions.py
```
Note both line numbers (use these as anchors for the next step).

- [ ] **Step 2: Reduce `_GBM_SPARSE_FIELDS` to drop the 7 cross-arm fields**

Edit `_GBM_SPARSE_FIELDS` tuple. **Remove** these 7 entries:
- `"transport_confidence"`
- `"reaction_id"`
- `"reaction_name"`
- `"ec_numbers"`
- `"mass_balance"`
- `"tcdb_family_id"`
- `"tcdb_family_name"`

**Keep** these (they remain sparse-stripped):
- `"gene_name"`, `"product"` — KG nulls
- `"metabolite_formula"`, `"metabolite_mass"`, `"metabolite_chebi_id"` — KG-coverage sparse
- `"gene_category"`, `"metabolite_inchikey"`, `"metabolite_smiles"`, `"metabolite_mnxm_id"`, `"metabolite_hmdb_id"`, `"reaction_mnxr_id"`, `"reaction_rhea_ids"`, `"tcdb_level_kind"`, `"tc_class_id"` — verbose-only sparse

Resulting tuple (final value):

```python
_GBM_SPARSE_FIELDS = (
    "gene_name",
    "product",
    "metabolite_formula",
    "metabolite_mass",
    "metabolite_chebi_id",
    # verbose fields — sparse-strip when null on the other arm or
    # when KG simply has no value
    "gene_category",
    "metabolite_inchikey",
    "metabolite_smiles",
    "metabolite_mnxm_id",
    "metabolite_hmdb_id",
    "reaction_mnxr_id",
    "reaction_rhea_ids",
    "tcdb_level_kind",
    "tc_class_id",
)
```

- [ ] **Step 3: Verify `_MBG_SPARSE_FIELDS = _GBM_SPARSE_FIELDS` alias still holds**

Run:
```bash
grep -n "_MBG_SPARSE_FIELDS = " multiomics_explorer/api/functions.py
```
Expected: `_MBG_SPARSE_FIELDS = _GBM_SPARSE_FIELDS` (single-line alias). No edit needed — alias picks up the new tuple automatically.

- [ ] **Step 4: Run the failing tests — they should now PASS**

Run:
```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite::test_cross_arm_fields_none_padded tests/unit/test_api_functions.py::TestMetabolitesByGene::test_cross_arm_fields_none_padded -v
```
Expected: both PASS.

- [ ] **Step 5: Run full GBM + MBG API-test suites — surface any regressions**

Run:
```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite tests/unit/test_api_functions.py::TestMetabolitesByGene -v
```
Expected: all PASS. If any test fails because it asserted "key absent" on a cross-arm field (e.g., `assert "tcdb_family_id" not in row` on a metabolism row), proceed to Step 6.

- [ ] **Step 6: If any existing tests fail with "assert X not in row" patterns, update them**

Locate via:
```bash
grep -n "assert .* not in .*\(transport_confidence\|tcdb_family\|reaction_id\|reaction_name\|ec_numbers\|mass_balance\)" tests/unit/test_api_functions.py
```

For each match, change the assertion from "key absent" to "key present, value None":
- Before: `assert "tcdb_family_id" not in row`
- After: `assert row["tcdb_family_id"] is None`

If no matches found, skip this step.

- [ ] **Step 7: Re-run the full GBM + MBG suite — confirm green**

```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite tests/unit/test_api_functions.py::TestMetabolitesByGene -v
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "fix(api): None-pad cross-arm fields on GBM + MBG result rows (Item 6.1)

Reduce _GBM_SPARSE_FIELDS to remove 7 cross-arm keys. Every row in
results now carries the full cross-arm key set; metabolism rows have
transport_confidence/tcdb_family_id/tcdb_family_name = None, transport
rows have reaction_id/reaction_name/ec_numbers/mass_balance = None.

Spec: docs/tool-specs/2026-05-05-phase3-compound-anchored-tightening.md §6.1"
```

---

### Task 3: Add wrapper-layer test that envelope serializes None values explicitly

**Files:**
- Modify: `tests/unit/test_tool_wrappers.py` (add tests inside `TestGenesByMetaboliteWrapper` and `TestMetabolitesByGeneWrapper`)

- [ ] **Step 1: Add `test_envelope_serializes_none_cross_arm_fields` to TestGenesByMetaboliteWrapper**

Locate via:
```bash
grep -n "^class TestGenesByMetaboliteWrapper" tests/unit/test_tool_wrappers.py
```

Add a new test method:

```python
async def test_envelope_serializes_none_cross_arm_fields(self, monkeypatch):
    """After Item 6.1: model_dump() of the response must NOT strip None
    values from cross-arm fields. Default Pydantic v2 behavior preserves
    None on Optional fields — verify no `exclude_none=True` is added on
    the wrapper response path.
    """
    # Construct a synthetic raw API response with one metabolism + one transport row
    raw = {
        "total_matching": 2,
        "returned": 2,
        "offset": 0,
        "truncated": False,
        "warnings": [],
        "not_found": {"metabolite_ids": [], "organism": None, "metabolite_pathway_ids": []},
        "not_matched": [],
        "by_metabolite": [],
        "by_evidence_source": [],
        "by_transport_confidence": [],
        "top_reactions": [],
        "top_tcdb_families": [],
        "top_gene_categories": [],
        "top_genes": [],
        "gene_count_total": 1,
        "reaction_count_total": 1,
        "transporter_count_total": 1,
        "metabolite_count_total": 1,
        "results": [
            {
                "locus_tag": "PMM0001",
                "evidence_source": "metabolism",
                "transport_confidence": None,  # None preserved
                "reaction_id": "kegg.reaction:R00131",
                "reaction_name": "test reaction",
                "ec_numbers": ["3.5.1.5"],
                "mass_balance": "balanced",
                "tcdb_family_id": None,        # None preserved
                "tcdb_family_name": None,       # None preserved
                "metabolite_id": "kegg.compound:C00086",
                "metabolite_name": "Urea",
            },
            {
                "locus_tag": "PMM0392",
                "evidence_source": "transport",
                "transport_confidence": "family_inferred",
                "reaction_id": None,             # None preserved
                "reaction_name": None,            # None preserved
                "ec_numbers": None,               # None preserved
                "mass_balance": None,             # None preserved
                "tcdb_family_id": "tcdb:3.A.1",
                "tcdb_family_name": "ABC superfamily",
                "metabolite_id": "kegg.compound:C00086",
                "metabolite_name": "Urea",
            },
        ],
    }

    monkeypatch.setattr(api, "genes_by_metabolite", lambda *a, **kw: raw)

    # Call wrapper and assert serialized envelope preserves None
    response = await self._call_wrapper(metabolite_ids=["kegg.compound:C00086"], organism="MED4")
    dumped = response.model_dump()

    metab_row = next(r for r in dumped["results"] if r["evidence_source"] == "metabolism")
    transp_row = next(r for r in dumped["results"] if r["evidence_source"] == "transport")

    # Cross-arm None values must be present, not stripped
    assert metab_row["transport_confidence"] is None
    assert metab_row["tcdb_family_id"] is None
    assert metab_row["tcdb_family_name"] is None
    assert transp_row["reaction_id"] is None
    assert transp_row["reaction_name"] is None
    assert transp_row["ec_numbers"] is None
    assert transp_row["mass_balance"] is None
```

(Use the existing `_call_wrapper` helper or fixture pattern in the test class. If the class uses a different pattern, adapt — the assertion shape is what matters.)

- [ ] **Step 2: Add the equivalent test to TestMetabolitesByGeneWrapper**

Locate via:
```bash
grep -n "^class TestMetabolitesByGeneWrapper" tests/unit/test_tool_wrappers.py
```

Add a structurally identical test, swapping `genes_by_metabolite` for `metabolites_by_gene` and the input kwarg from `metabolite_ids` to `locus_tags`. The shared `GeneReactionMetaboliteTriplet` row class means the assertion shape is identical.

- [ ] **Step 3: Run the new wrapper tests**

Run:
```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestGenesByMetaboliteWrapper::test_envelope_serializes_none_cross_arm_fields tests/unit/test_tool_wrappers.py::TestMetabolitesByGeneWrapper::test_envelope_serializes_none_cross_arm_fields -v
```
Expected: both PASS — Pydantic v2 default `model_dump()` does NOT strip None on Optional fields, so this test passes immediately on the post-Task-2 code. The test exists to LOCK this behavior — a future `exclude_none=True` accidental addition would fail it.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_tool_wrappers.py
git commit -m "test: lock None-preservation on wrapper envelope serialization (Item 6.1)

Pydantic v2 model_dump() preserves None on Optional fields by default.
This test exists to catch a future regression where someone might
accidentally add exclude_none=True on the wrapper response path."
```

---

### Task 4: Item 1 docstring updates — Pydantic class + tool docstrings

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` — `GeneReactionMetaboliteTriplet` class docstring + per-field cross-arm descriptions + GBM/MBG MCP tool docstrings

- [ ] **Step 1: Locate `GeneReactionMetaboliteTriplet` class**

```bash
grep -n "^class GeneReactionMetaboliteTriplet" multiomics_explorer/mcp_server/tools.py
```

- [ ] **Step 2: Update the class docstring**

Find this current text in the class docstring:

> All per-arm-specific fields are Optional and sparse-stripped at the api/ layer when null.

Replace with:

> All per-arm-specific fields are Optional and explicitly `None` on rows from the other arm — every row carries identical keys.

Use the Edit tool with the exact old text → exact new text.

- [ ] **Step 3: Verify per-field descriptions for cross-arm fields are still accurate**

Read the field descriptions for `transport_confidence`, `reaction_id`, `reaction_name`, `ec_numbers`, `mass_balance`, `tcdb_family_id`, `tcdb_family_name`. Each should already say something like "None on metabolism rows" / "Metabolism rows only" / "Transport rows only". If any field's description is now stale (e.g., still says "stripped when null"), update it to "Always present; None on rows from the other arm." (verbatim, kept consistent across all 7 fields).

- [ ] **Step 4: Add union-shape paragraph to GBM MCP tool docstring**

Locate the `genes_by_metabolite` tool docstring:
```bash
grep -n "async def genes_by_metabolite" multiomics_explorer/mcp_server/tools.py
```

Read the docstring. Add this paragraph immediately before the `Args:` section (or near the end of the description block, wherever fits the existing docstring style):

```
Per-row schema (union shape):
    Every row carries the full cross-arm key set. Metabolism-arm rows
    have `transport_confidence` / `tcdb_family_id` / `tcdb_family_name`
    = None; transport-arm rows have `reaction_id` / `reaction_name` /
    `ec_numbers` / `mass_balance` = None. Use `row['key']` (KeyError-free)
    rather than `row.get('key')` if the difference matters to you.
```

- [ ] **Step 5: Add the same paragraph to MBG MCP tool docstring**

Locate via:
```bash
grep -n "async def metabolites_by_gene" multiomics_explorer/mcp_server/tools.py
```

Add the identical paragraph (the row class is shared, so the same wording applies).

- [ ] **Step 6: Run the GBM/MBG test suites once more — sanity check**

```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite tests/unit/test_api_functions.py::TestMetabolitesByGene tests/unit/test_tool_wrappers.py::TestGenesByMetaboliteWrapper tests/unit/test_tool_wrappers.py::TestMetabolitesByGeneWrapper -v
```
Expected: all PASS — docstring changes are non-behavioral.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "docs(mcp): document union-shape per-row schema on GBM + MBG (Item 6.1)

GeneReactionMetaboliteTriplet class docstring + GBM + MBG MCP tool
docstrings now explicitly state the union-shape contract (every row
carries identical keys, cross-arm fields are None on the other arm)."
```

---

## Item 2 — Reaction-arm reversibility framing

### Task 5: Reaction-arm reversibility framing — row class + tool docstrings + field descriptions

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` — `GeneReactionMetaboliteTriplet` class docstring + `reaction_id` / `reaction_name` field descriptions + GBM/MBG MCP tool docstrings

**Canonical phrasing (use verbatim, lock at spec freeze):**

> Reaction edges are undirected AND carry no reversibility flag — interpret all reaction-arm rows as 'involved in', never 'produces' / 'consumes' / 'reversible'. (KG limitation: KEGG-anchored reactions lack both direction and `is_reversible`; see audit §4.1.1 + §4.1.2.)

- [ ] **Step 1: Add the canonical phrasing to `GeneReactionMetaboliteTriplet` class docstring**

Locate the class docstring (already touched in Task 4, Step 2). Add the canonical phrasing as a new paragraph immediately after the union-shape paragraph from Task 4, Step 2.

- [ ] **Step 2: Suffix the canonical-phrasing reference to `reaction_id` and `reaction_name` Field descriptions**

For each of the two fields, append this suffix to the existing description:

```
Metabolism rows only — see class-level note on undirected, non-reversible interpretation.
```

If the existing description already says "Metabolism rows only", just add the cross-reference: `— see class-level note on undirected, non-reversible interpretation.`

- [ ] **Step 3: Add a "Reaction-arm framing" paragraph to GBM MCP tool docstring**

Locate `async def genes_by_metabolite` (already located in Task 4, Step 4). Add this paragraph immediately before the `Args:` section:

```
Reaction-arm framing:
    Reaction edges are undirected AND carry no reversibility flag —
    interpret all reaction-arm rows as 'involved in', never 'produces'
    / 'consumes' / 'reversible'. (KG limitation: KEGG-anchored reactions
    lack both direction and `is_reversible`; see audit §4.1.1 + §4.1.2.)
```

- [ ] **Step 4: Add the same paragraph to MBG MCP tool docstring**

Locate `async def metabolites_by_gene` (already located in Task 4, Step 5). Add the identical paragraph (verbatim).

- [ ] **Step 5: Run the GBM/MBG test suites — sanity check**

```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite tests/unit/test_api_functions.py::TestMetabolitesByGene -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "docs(mcp): reaction-arm reversibility framing on GBM + MBG (Item 6.2)

Document explicitly that reaction edges are undirected AND carry no
reversibility flag — reaction-arm rows are 'involved in', never
'produces'/'consumes'/'reversible'. KEGG-anchored reactions lack both
upstream (audit §4.1.1 + §4.1.2 RESOLVED — KG limitation is permanent)."
```

---

## Item 3 — family_inferred-dominance warning rewrite

### Task 6: Write failing tests for the new warning text (TDD red)

**Files:**
- Modify: `tests/unit/test_api_functions.py` — update `test_family_inferred_dominance_warning_fires` in both `TestGenesByMetabolite` and `TestMetabolitesByGene` to assert the new text format

**New warning text (both tools, symmetric):**

```
Most transport rows are `family_inferred` ({fi_count} of {fi_count + sc_count}) — annotations rolled up from family-level transport potential. Workflow-dependent: use `transport_confidence='substrate_confirmed'` for conservative-cast questions (e.g. cross-organism inference); keep `family_inferred` for broad-screen candidate enumeration. Both tiers are annotations, neither is ground truth — see analysis-doc §g.
```

(`fi_count` = `transport_fi_total`; `sc_count` = `transport_sc_total`.)

- [ ] **Step 1: Locate the existing GBM warning test**

```bash
grep -n "test_family_inferred_dominance_warning_fires" tests/unit/test_api_functions.py
```

You'll find one inside `TestGenesByMetabolite` (~line 7315 pre-Phase-1+2; verify current line) and one inside `TestMetabolitesByGene` (~line 8243 pre-Phase-1+2).

- [ ] **Step 2: Update the GBM warning test to assert the new text**

In `TestGenesByMetabolite.test_family_inferred_dominance_warning_fires`, replace the current warning-text assertion with:

```python
# Assert the new symmetric warning format (Item 6.3)
warning = warnings[0]
assert "Most transport rows are `family_inferred`" in warning
assert "annotations rolled up from family-level transport potential" in warning
assert "Workflow-dependent" in warning
assert "Both tiers are annotations, neither is ground truth" in warning
assert "analysis-doc §g" in warning

# Assert the inline counts ARE present (X of Y format)
import re
m = re.search(r"\((\d+) of (\d+)\)", warning)
assert m, f"warning must include `(X of Y)` count format; got: {warning}"
fi_count, total = int(m.group(1)), int(m.group(2))
assert fi_count > total - fi_count, "fi_count must dominate (test setup)"

# Assert old "high-precision" prescription is GONE
assert "high-precision" not in warning
assert "substrate-curated transporter genes only" not in warning
```

- [ ] **Step 3: Update the MBG warning test identically**

In `TestMetabolitesByGene.test_family_inferred_dominance_warning_fires`, apply the same changes — the assertion block is byte-identical (the warnings are now symmetric).

- [ ] **Step 4: Run the two updated tests, confirm they FAIL**

```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite::test_family_inferred_dominance_warning_fires tests/unit/test_api_functions.py::TestMetabolitesByGene::test_family_inferred_dominance_warning_fires -v
```
Expected: both FAIL with `AssertionError: assert "Most transport rows are \`family_inferred\`" in warning` — the current warning strings do NOT match the new format.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/unit/test_api_functions.py
git commit -m "test: assert new family_inferred-warning text on GBM + MBG (Item 6.3, TDD red)"
```

---

### Task 7: Rewrite the warning strings (TDD green)

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — both warning string sites

- [ ] **Step 1: Locate the GBM warning**

```bash
grep -n "Majority of transport rows are family_inferred" multiomics_explorer/api/functions.py
```

- [ ] **Step 2: Replace the GBM warning with the new symmetric phrasing**

Find this block (the GBM warning):

```python
warnings.append(
    "Majority of transport rows are family_inferred (rolled-up "
    "from broad TCDB families). Re-run with "
    "transport_confidence='substrate_confirmed' for "
    "substrate-curated transporter genes only."
)
```

Replace with:

```python
warnings.append(
    f"Most transport rows are `family_inferred` ({transport_fi_total} of "
    f"{transport_fi_total + transport_sc_total}) — annotations rolled up from "
    "family-level transport potential. Workflow-dependent: use "
    "`transport_confidence='substrate_confirmed'` for "
    "conservative-cast questions (e.g. cross-organism inference); "
    "keep `family_inferred` for broad-screen candidate enumeration. "
    "Both tiers are annotations, neither is ground truth — see "
    "analysis-doc §g."
)
```

(Variables `transport_fi_total` and `transport_sc_total` already exist in scope at this site — verify before editing.)

- [ ] **Step 3: Locate the MBG warning**

```bash
grep -n "Transport rows in this slice are dominated by" multiomics_explorer/api/functions.py
```

- [ ] **Step 4: Replace the MBG warning with the new symmetric phrasing**

Find this block (the MBG warning):

```python
warnings.append(
    f"Transport rows in this slice are dominated by "
    f"`family_inferred` rollup ({transport_fi_total} of "
    f"{transport_fi_total + transport_sc_total} transport rows). "
    "For high-precision substrate-curated annotations only, set "
    "`transport_confidence='substrate_confirmed'` and/or "
    "`evidence_sources=['transport']`."
)
```

Replace with the **byte-identical** new symmetric phrasing (same as the GBM replacement):

```python
warnings.append(
    f"Most transport rows are `family_inferred` ({transport_fi_total} of "
    f"{transport_fi_total + transport_sc_total}) — annotations rolled up from "
    "family-level transport potential. Workflow-dependent: use "
    "`transport_confidence='substrate_confirmed'` for "
    "conservative-cast questions (e.g. cross-organism inference); "
    "keep `family_inferred` for broad-screen candidate enumeration. "
    "Both tiers are annotations, neither is ground truth — see "
    "analysis-doc §g."
)
```

- [ ] **Step 5: Run the failing tests — they should now PASS**

```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite::test_family_inferred_dominance_warning_fires tests/unit/test_api_functions.py::TestMetabolitesByGene::test_family_inferred_dominance_warning_fires -v
```
Expected: both PASS.

- [ ] **Step 6: Run the full GBM + MBG suite — confirm no regressions**

```bash
uv run pytest tests/unit/test_api_functions.py::TestGenesByMetabolite tests/unit/test_api_functions.py::TestMetabolitesByGene -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/api/functions.py
git commit -m "fix(api): rewrite family_inferred-dominance warning, symmetric across GBM + MBG (Item 6.3)

Replace 'high-precision' prescription with question-shape-aware framing
(workflow-dependent — substrate_confirmed for conservative cast,
family_inferred for broad screen; both tiers are annotations, neither
is ground truth). GBM and MBG now emit byte-identical text (modulo
count variables — both already use transport_fi_total / transport_sc_total)."
```

---

### Task 8: Verify precision_tier scenario removal (NO-OP — already done)

**Files:** none — verification only.

Item 6.3 spec calls for dropping the `precision_tier` scenario from `examples/metabolites.py`. Verified 2026-05-06 that this is already complete; only confirm the absence and check the analysis doc for stale references.

- [ ] **Step 1: Confirm `examples/metabolites.py` has no `precision_tier` scenario**

```bash
grep -n "scenario_precision_tier\|precision_tier" examples/metabolites.py
```
Expected: empty output. If not empty, halt and report — the spec assumes removal is complete.

- [ ] **Step 2: Confirm `tests/integration/test_examples.py` has no `precision_tier` parametrize entry**

```bash
grep -n "precision_tier" tests/integration/test_examples.py 2>/dev/null
```
Expected: empty output. If not empty, drop the entry from the parametrize list.

- [ ] **Step 3: Check the analysis doc for `precision_tier` / A7 references**

```bash
grep -n "precision_tier\|A7" multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
```
Expected: empty output. (If any references remain, they'll be cleaned up in Task 11 along with other analysis-doc edits.)

- [ ] **Step 4: No commit** — this task is verification-only.

---

## Item 4 — `by_element` / `elements` semantics docstring

### Task 9: by_element / elements semantics docstring updates

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` — `MbgByElement` class docstring + `MbgByElement.metabolite_count` Field description + `MetabolitesByGeneResponse.by_element` Field description + `list_metabolites` row class `elements` Field description + GBM/MBG/list_metabolites MCP tool docstrings

**Canonical phrasing (use verbatim):**

> Presence-only — count of distinct compounds containing each element at all. NOT stoichiometric (no atom counts per compound; stoichiometry lives in `metabolite.formula`). NOT mass-balanced (KG carries no substrate-vs-product role on `Reaction_has_metabolite`, see audit §4.1.1).

- [ ] **Step 1: Locate the four target sites in `tools.py`**

```bash
grep -n "^class MbgByElement\|class.*ListMetabolitesResponse\|by_element: list\|elements: list" multiomics_explorer/mcp_server/tools.py
```
Note all four anchors:
- `MbgByElement` class
- `MetabolitesByGeneResponse.by_element` envelope field (inside `MetabolitesByGeneResponse`)
- `list_metabolites` row class (the metabolite row that has `elements: list[str]` field — typically inside `ListMetabolitesResult` or similar; verify exact class name via grep)
- The `MbgByElement.metabolite_count` field description (inside `MbgByElement` class body)

- [ ] **Step 2: Append canonical phrasing to `MbgByElement` class docstring**

Find the `MbgByElement` class docstring. Append the canonical phrasing at the end of the docstring (before the closing `"""`).

- [ ] **Step 3: Append canonical phrasing to `MbgByElement.metabolite_count` Field description**

Find the `metabolite_count` field inside `MbgByElement` class. Its current `description=` ends with something about "Distinct metabolites in the filtered slice that contain this element." Append: ` Presence-only count — see class docstring for "not stoichiometric, not mass-balanced" semantics.`

- [ ] **Step 4: Append canonical phrasing to `MetabolitesByGeneResponse.by_element` Field description**

Find the `by_element` envelope-key Field inside `MetabolitesByGeneResponse`. Append the canonical phrasing to its existing `description=` text.

- [ ] **Step 5: Append a one-line note to the `list_metabolites` row's `elements` Field description**

Find the `elements: list[str] = Field(default_factory=list, description=...)` line for the list_metabolites metabolite row. Append: ` Presence list (no atom counts; stoichiometry lives in `formula`).`

- [ ] **Step 6: Add a one-line summary to the MBG MCP tool docstring**

Locate `async def metabolites_by_gene` (already touched in Tasks 4-5). In the section of the docstring where `by_element` is mentioned (or where envelope fields are summarized), add: `by_element: presence-only element-presence rollup (NOT stoichiometric, NOT mass-balanced).`

- [ ] **Step 7: Add a one-line summary to the list_metabolites MCP tool docstring**

```bash
grep -n "async def list_metabolites" multiomics_explorer/mcp_server/tools.py
```

In the section of the docstring where the `elements` filter (input) or row's `elements` field is mentioned, add a parenthetical: `(presence list, not stoichiometric — atom counts live in formula)`.

- [ ] **Step 8: Run unit tests on the affected wrappers — sanity check**

```bash
uv run pytest tests/unit/test_tool_wrappers.py -k "MetabolitesByGene or ListMetabolites" -v
```
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "docs(mcp): document by_element / elements presence-only semantics (Item 6.4)

Append canonical phrasing to MbgByElement class docstring + .metabolite_count
Field description + MetabolitesByGeneResponse.by_element Field + list_metabolites
row's elements Field + GBM/MBG/list_metabolites MCP tool docstrings.

Presence-only — counts distinct compounds containing each element.
NOT stoichiometric. NOT mass-balanced. Aligns with audit §4.1.1
(Reaction_has_metabolite carries no substrate-vs-product role)."
```

---

## Items 2 + 3 + 6 — Analysis-doc edits

### Task 10: Analysis-doc edits — Track A1 reversibility extension + top_genes fix

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md`

- [ ] **Step 1: Locate the Track A1 caveat section**

```bash
grep -n "involved in\|directional\|Track A1" multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
```

Find the existing direction caveat — the paragraph in Track A1 that says reaction edges have no direction.

- [ ] **Step 2: Extend the direction caveat to also call out the reversibility gap**

In the same paragraph, add a sentence:

> Combined with the absence of an `is_reversible` flag on Reaction nodes (audit §4.1.2 RESOLVED — KEGG lacks reversibility upstream), this means reaction-arm rows must be read as 'involved in' permanently, never 'produces' / 'consumes' / 'reversibly interconverts'.

(Adapt phrasing to match the existing paragraph's style. The information content is what matters.)

- [ ] **Step 3: Locate and fix the top_genes reference**

```bash
grep -n 'chem\["top_genes"\]\|top_genes' multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
```
Expected: one match at line 216 (`locus_tags = [g["locus_tag"] for g in chem["top_genes"]]`).

- [ ] **Step 4: Replace `chem["top_genes"]` with `chem["by_gene"]`**

Edit line 216 (or wherever the match is). Change:

```python
locus_tags = [g["locus_tag"] for g in chem["top_genes"]]
```

To:

```python
locus_tags = [g["locus_tag"] for g in chem["by_gene"]]
```

- [ ] **Step 5: Verify by running grep again**

```bash
grep -n "top_genes" multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
```
Expected: empty output (the `top_genes` reference is gone).

- [ ] **Step 6: Verify no `precision_tier` references remain**

```bash
grep -n "precision_tier\|A7" multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
```
Expected: empty output.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
git commit -m "docs(analysis): reversibility extension + top_genes fix (Items 6.2, 6.6)

Track A1 direction caveat extended to call out the reversibility gap
(audit §4.1.2 RESOLVED). N-source workflow snippet at line 216
fixed: chem['top_genes'] -> chem['by_gene'] (MBG has no top_genes
field by design — by_gene is the per-input rollup; top_metabolites
is the gene-anchored mirror of GBM's top_genes)."
```

---

## About-content YAML edits

### Task 11: About-content for items 1-4 (3 YAMLs) + regen

**Files:**
- Modify: `multiomics_explorer/inputs/tools/genes_by_metabolite.yaml`
- Modify: `multiomics_explorer/inputs/tools/metabolites_by_gene.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_metabolites.yaml`
- Run: `uv run python scripts/build_about_content.py`

**Mistake entries to add (one per tool, per item):**

| Tool | Item 6.1 (None-padding) | Item 6.2 (reversibility) | Item 6.3 (warning rewrite) | Item 6.4 (element semantics) |
|---|---|---|---|---|
| `genes_by_metabolite` | YES | YES | Replace existing | — |
| `metabolites_by_gene` | YES | YES | Replace existing | YES |
| `list_metabolites` | — | — | — | YES |

- [ ] **Step 1: Edit `inputs/tools/genes_by_metabolite.yaml`**

Add three mistake entries (or extend examples / chaining as appropriate per existing YAML style):

**Item 6.1 mistake (new):**
> Every result row has the same key set — cross-arm fields are explicitly `None` on rows from the other arm (metabolism rows have `transport_confidence`/`tcdb_family_id`/`tcdb_family_name` = None; transport rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` = None). Use `row['transport_confidence']` (KeyError-free) rather than `row.get('transport_confidence')` if the difference matters.

**Item 6.2 mistake (new):**
> Reaction-arm rows are NOT directional — KG reactions carry neither a substrate-vs-product role on `Reaction_has_metabolite` nor an `is_reversible` flag. Read `evidence_source='metabolism'` rows as 'gene catalyses a reaction *involving* this metabolite,' never as 'produces X' / 'consumes Y' / 'reversibly interconverts'. The KG limitation is permanent (KEGG lacks both upstream).

**Item 6.3 mistake (replace existing "treat family_inferred as low-precision" entry):**
> When the auto-warning fires (most transport rows are `family_inferred`), interpret workflow-dependent: use `transport_confidence='substrate_confirmed'` for conservative-cast questions (e.g. cross-organism inference); keep `family_inferred` for broad-screen candidate enumeration (e.g. N-source DE — the real MED4 N-uptake genes are family_inferred-only). Both tiers are annotations, neither is ground truth — see analysis-doc §g.

(If an existing mistake entry uses "high-precision" or "treat family_inferred as low-precision" framing, REPLACE it with the new entry. Net change is zero new entries, one rewrite for Item 6.3.)

- [ ] **Step 2: Edit `inputs/tools/metabolites_by_gene.yaml`**

Add the same three mistake entries (Items 6.1, 6.2, 6.3 — same wording as Step 1 but adapted for the gene-anchored phrasing where natural). Plus one more for Item 6.4:

**Item 6.4 mistake (new):**
> `by_element` envelope is presence-only — count of distinct metabolites containing each element at all. NOT stoichiometric (atom counts live in `metabolite.formula`); NOT mass-balanced (KG `Reaction_has_metabolite` is undirected and carries no substrate/product role).

- [ ] **Step 3: Edit `inputs/tools/list_metabolites.yaml`**

Add only the Item 6.4 mistake entry:

**Item 6.4 mistake (new):**
> Per-row `elements` is a presence list — no atom counts per compound. Stoichiometry lives in `formula`. Filter on `elements` (e.g. `elements=['N']` for N-bearing compounds), never on `formula` substring (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N').

- [ ] **Step 4: Update example responses if they show stripped cross-arm rows**

If any example response in `genes_by_metabolite.yaml` or `metabolites_by_gene.yaml` shows a row WITHOUT cross-arm None keys, update one example to show the union shape (cross-arm None values present). This is a once-per-yaml verification.

- [ ] **Step 5: Regenerate about-content markdown**

```bash
uv run python scripts/build_about_content.py
```
Expected: completes cleanly, writes to `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{genes_by_metabolite,metabolites_by_gene,list_metabolites}.md`. No errors.

- [ ] **Step 6: Run unit tests — sanity check**

```bash
uv run pytest tests/unit/ -v -x --ignore=tests/integration
```
Expected: all PASS. (No about-content tests typically fail on YAML changes; this is a defensive sweep.)

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/inputs/tools/{genes_by_metabolite,metabolites_by_gene,list_metabolites}.yaml multiomics_explorer/skills/multiomics-kg-guide/references/tools/
git commit -m "docs(about): about-content for compound-anchored tightening (Items 6.1-6.4)

Three YAMLs touched. New mistake entries for None-padding (6.1),
reaction-arm reversibility framing (6.2), workflow-dependent
family_inferred reading (6.3 — replaces existing high-precision entry),
by_element / elements presence-only semantics (6.4).

Regenerated via scripts/build_about_content.py."
```

---

## Regression fixture regen

### Task 12: Regenerate regression fixtures (Items 6.1 + 6.3)

**Files:**
- Modify: `tests/regression/` (fixture files regenerated by `--force-regen`)

- [ ] **Step 1: Run regression suite without regen — observe expected mismatches**

```bash
uv run pytest tests/regression/ -m kg -q
```
Expected: failures on GBM + MBG fixtures (rows now wider — None-padded cross-arm fields), and on any fixture capturing the family_inferred-dominance warning text. **Do not panic — these are the expected mismatches.**

- [ ] **Step 2: Force-regen**

```bash
uv run pytest tests/regression/ --force-regen -m kg -q
```
Expected: regenerates all fixtures; exits clean.

- [ ] **Step 3: Re-run regression suite without `--force-regen` — confirm clean**

```bash
uv run pytest tests/regression/ -m kg -q
```
Expected: all PASS. Zero diff.

- [ ] **Step 4: Inspect a sample of regenerated fixtures for sanity**

Pick one GBM fixture file and verify visually that:
- Result rows now carry `transport_confidence: null` (or the YAML/JSON serialization equivalent) on metabolism rows.
- Result rows carry `reaction_id: null` on transport rows.
- The warning text (where present) is the new symmetric format starting with "Most transport rows are `family_inferred`".

```bash
# Replace <fixture-file> with an actual GBM fixture path, e.g.:
ls tests/regression/ | head -20
# then read one
```

- [ ] **Step 5: Add explicit lock-in regression assertions** (one per tool)

If the regression suite supports adding ad-hoc assertion files (per the existing convention — check by listing the regression/ tree), add:

- One regression case per tool (GBM + MBG) asserting every result row has all 7 cross-arm keys present (some `None`); a metabolism row has `transport_confidence`/`tcdb_family_id`/`tcdb_family_name` all `None`; a transport row has `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` all `None`. Non-cross-arm sparse fields continue to strip — actual row width varies fixture-to-fixture, so DO NOT assert on a single field count.
- One regression case per tool asserting the new warning text on a known family_inferred-dominated input.

If the regression suite doesn't have a clean per-case-assertion mechanism (it's all auto-generated fixtures with diff-based assertions), skip Step 5 — the regenerated fixtures themselves serve as the lock-in.

- [ ] **Step 6: Commit**

```bash
git add tests/regression/
git commit -m "test(regression): regen fixtures for Phase 3 (Items 6.1, 6.3)

GBM + MBG fixtures regenerated to reflect None-padded cross-arm fields
(rows now carry full key set). Warning-text fixtures regenerated to
the new symmetric phrasing.

Force-regen: pytest tests/regression/ --force-regen -m kg -q."
```

---

## CLAUDE.md tool-table touch-ups

### Task 13: Update CLAUDE.md tool-table prose for affected tools

**Files:**
- Modify: `CLAUDE.md`

The CLAUDE.md tool table has one row per tool with prose summarizing its surface. Three rows need touch-ups (only where row prose currently mentions warning text, row shape, or element semantics):

- [ ] **Step 1: Locate the three affected rows**

```bash
grep -n "genes_by_metabolite\|metabolites_by_gene\|list_metabolites" CLAUDE.md | head -20
```
Note the rows.

- [ ] **Step 2: Update `genes_by_metabolite` row**

If the row prose mentions:
- Cross-arm field stripping or "metabolism rows omit transport_confidence" — update to "every row carries full cross-arm key set; cross-arm fields = None on the other arm".
- "high-precision substrate-curated annotations" — update to "workflow-dependent — family_inferred is the broad-screen tier, substrate_confirmed is the conservative tier; both are annotations".

If neither applies (the row is silent on these aspects), no edit needed.

- [ ] **Step 3: Update `metabolites_by_gene` row**

Same checks as Step 2, plus:
- If the row prose mentions `by_element` rollup, append "(presence-only; not stoichiometric, not mass-balanced)" after the field name.

- [ ] **Step 4: Update `list_metabolites` row**

If the row prose mentions per-row `elements` field, append "(presence list, not stoichiometric)" after the field name. Otherwise, no edit needed.

- [ ] **Step 5: Confirm CLAUDE.md still parses cleanly**

```bash
# Defensive — the file is markdown, no parser run, just a visual check
head -100 CLAUDE.md
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): update tool-table prose for Phase 3 changes

Touch-ups for genes_by_metabolite, metabolites_by_gene, list_metabolites
where row prose mentions warning text, cross-arm row shape, or by_element
/ elements semantics. Items 6.1, 6.3, 6.4."
```

---

## Final verification

### Task 14: Full test suite + finish

**Files:** none — verification only.

- [ ] **Step 1: Run full unit test suite**

```bash
uv run pytest tests/unit/ -v
```
Expected: all PASS.

- [ ] **Step 2: Run KG-integration suite**

```bash
uv run pytest tests/integration/ -m kg -v
```
Expected: all PASS. (Phase 3 has no new KG-integration tests, but existing ones must not regress.)

- [ ] **Step 3: Run regression suite (no regen)**

```bash
uv run pytest tests/regression/ -m kg -q
```
Expected: clean.

- [ ] **Step 4: Sanity-check regenerated about-content**

```bash
uv run python scripts/build_about_content.py
git status
```
Expected: clean working tree (about-content was regenerated and committed in Task 11; no diff now).

- [ ] **Step 5: Verify the spec's acceptance criteria one-by-one**

Open `docs/tool-specs/2026-05-05-phase3-compound-anchored-tightening.md` §11 acceptance criteria. Verify each bullet:
- All 5 active items landed (1, 2, 3, 4, 6) ✓
- Item 6.1: every row has all 7 cross-arm keys ✓
- Item 6.2: row class + field descriptions + tool docstrings + YAML + analysis doc carry reversibility framing ✓
- Item 6.3: GBM + MBG warnings byte-identical (modulo count vars); no "high-precision" prescription ✓
- Item 6.4: MbgByElement + envelope-key + list_metabolites elements field carry presence-only phrasing ✓
- Item 6.5: DROPPED — confirm via `git grep "query.*Annotated" mcp_server/tools.py | grep -v run_cypher` shows nothing new ✓
- Item 6.6: `analysis/metabolites.md` no longer references `chem["top_genes"]` ✓
- All unit + KG-integration + regression suites pass ✓
- About-content YAML edits regenerate cleanly ✓
- CLAUDE.md updated ✓
- `examples/metabolites.py` no longer has `precision_tier` (was already true pre-task) ✓

- [ ] **Step 6: Confirm Item 6.5 drop — defensive grep**

```bash
git grep "query.*Annotated\|query: str.*None" multiomics_explorer/mcp_server/tools.py multiomics_explorer/api/functions.py | grep -v "run_cypher\|class.*Query"
```
Expected: empty output. (No new `query=` kwargs added to any list/search tool.)

- [ ] **Step 7: Push the worktree branch + open PR**

```bash
git push -u origin <branch-name>
gh pr create --title "Phase 3: Compound-anchored tightening + ergonomics (5 items)" --body "$(cat <<'EOF'
## Summary

Phase 3 of the metabolites surface refresh roadmap — compound-anchored
tightening + ergonomics. 5 active items (Item 5 was DROPPED 2026-05-06):

- **Item 6.1**: GBM + MBG result rows now carry all 7 cross-arm keys
  (None on the other arm) — predictable per-row schema for downstream
  consumers.
- **Item 6.2**: Reaction-arm reversibility framing — explicit
  "involved in" interpretation in row class + tool docstrings + analysis
  doc Track A1 (audit §4.1.1 + §4.1.2 RESOLVED).
- **Item 6.3**: family_inferred-dominance warning rewritten to
  workflow-dependent framing on both GBM + MBG (byte-identical text;
  drops the "high-precision" prescription).
- **Item 6.4**: by_element / elements semantics docstring — presence-only,
  not stoichiometric, not mass-balanced.
- **Item 6.6**: Single-line analysis-doc fix —
  `chem["top_genes"]` → `chem["by_gene"]`.

Spec: `docs/tool-specs/2026-05-05-phase3-compound-anchored-tightening.md`
Plan: `docs/superpowers/plans/2026-05-06-phase3-compound-anchored-tightening.md`

## Test plan

- [x] Unit tests pass (TestGenesByMetabolite + TestMetabolitesByGene + wrappers).
- [x] KG-integration tests pass (no regressions).
- [x] Regression fixtures regenerated and clean.
- [x] About-content YAMLs regen cleanly via build_about_content.py.
- [x] No `query=` kwargs added (Item 5 dropped — defensive grep).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

(Confirm with the user before pushing if this is a fresh branch; PR creation requires `gh` CLI authenticated.)

- [ ] **Step 8: No commit** — task is verification + handoff.

---

## Self-review checklist (run before declaring plan complete)

- [x] Every spec section/item maps to at least one task: §6.1→Tasks 1-4; §6.2→Tasks 5, 10; §6.3→Tasks 6-8, 11; §6.4→Task 9; §6.5→DROPPED; §6.6→Task 10.
- [x] No placeholders, no "TBD", no "similar to Task N" without inlined code.
- [x] Method/property names consistent across tasks: `_GBM_SPARSE_FIELDS`, `_MBG_SPARSE_FIELDS`, `transport_confidence`, `tcdb_family_id`, `tcdb_family_name`, `reaction_id`, `reaction_name`, `ec_numbers`, `mass_balance` — used identically throughout.
- [x] TDD discipline preserved on testable behavior changes (Items 6.1, 6.3); pure-docstring items (6.2, 6.4, 6.6) are no-test.
- [x] Anchor patterns over line numbers throughout (line numbers in spec are stale post-Phase-1+2 land; plan grep's anchor names at edit time).
- [x] Frequent commits — one per logical step.
- [x] Final verification task (14) confirms acceptance criteria from spec §11.
