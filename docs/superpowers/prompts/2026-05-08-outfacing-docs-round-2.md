# Follow-up prompt: outfacing-docs readability pass — round 2

**Context — round 1 recap:**

The 2026-05-07 readability pass swept the MCP outfacing surface (37 tool
docstrings + Pydantic `Field(description=...)` + per-tool YAMLs) per 9
style rules, then a follow-up sweep added a `--lint` mode in
`scripts/build_about_content.py` plus a per-tool parametrized pytest
gate, plus orchestrator-skill updates so future tool work picks up the
rules. Cross-refs:

- Round 1 spec: [docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md](../specs/2026-05-07-mcp-docs-readability-pass-design.md)
- Round 1 follow-up prompt: [2026-05-07-mcp-readability-followups.md](2026-05-07-mcp-readability-followups.md)
- Surface map: [.claude/skills/layer-rules/references/layer-boundaries.md](../../../.claude/skills/layer-rules/references/layer-boundaries.md)

**What round 2 covers:**

The layer-rules surface map flagged three more outfacing surfaces that
the round-1 pass did not touch (the spec listed them as out of scope) —
plus one surface that the map missed entirely. This round closes the
loop: extend the lint to cover them, sweep the violations, and update
the skills so the next tool addition is born compliant across every
outfacing surface.

---

## Inventory

Lint-equivalent scan against current state:

| Surface | Files | Violations | Mounted as |
|---|---|---|---|
| `multiomics_explorer/api/functions.py` (docstrings) | 1 | ~100-300 expected (~20 in head sample) | `from multiomics_explorer import {fn}` (package import); indirectly via rendered md "Package import equivalent" path |
| `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/*.md` | 3 (derived_metrics, enrichment, metabolites) | 38 (3 + 9 + 26) | `docs://analysis/{name}` |
| `multiomics_explorer/skills/multiomics-kg-guide/references/guide/*.md` | 4 (start_here, concepts, conventions, python_api) | 5 (3 + 2) | `docs://guide/{name}` |
| `examples/*.py` + `examples/README.md` | 3 | 11 (in metabolites.py) | `docs://examples/{file}` (whole file is what agents read) |

Densest violator: `analysis/metabolites.md` (26 hits — `Part 4 §4.1.1`,
`audit §4.1.2`, `Phase 2`, `KG-A5`, `KG-MET-011`, `KG release 2026-05-05`,
`§b2`, `§g`).

The work splits into four stages, ordered so each stage's output unlocks
the next.

---

## Stage A — Surface map correction (1 commit)

**Goal:** the surface map in
[layer-boundaries.md](../../../.claude/skills/layer-rules/references/layer-boundaries.md)
must reflect the four-surface reality before any code or sweep work, so
implementers and reviewers downstream read the correct rules.

**Spec:**

1. **Add row for `examples/*.py`.** The `mcp_server/server.py:105`
   mount point exposes the repo-root `examples/` directory at
   `docs://examples/{file}`. The **whole file** is read by agents (not
   just docstrings), since the file IS the runnable artifact. Source
   files live at the repo root, not in the skills tree —
   architecturally it's a separate root-level outfacing surface, worth
   a 1-line note alongside the table.
2. **Add row for `examples/README.md`.** Same mount.
3. **Drop softeners** on the `analysis/*.md` row ("(best-effort)") and
   `guide/*.md` row ("(rare edits)") — both surfaces had violations
   slip through (38 in analysis alone). They follow the same rules at
   the same weight as MCP surfaces.
4. **Add a "Scanner notes" paragraph below the table** clarifying lint
   mode per surface (the table itself is already wide; a paragraph is
   tighter than a 3rd column):

   > - Tool docstring + Pydantic `Field(description=...)`: caught
   >   indirectly via the rendered tool-md scan.
   > - `api/functions.py` docstrings: AST-extracted; `# ...` comments
   >   are not scanned (per the surface map row above).
   > - `examples/*.py`: whole file scanned line-by-line — comments
   >   ARE outfacing here, since the file IS the artifact.
   > - Hand-authored md (`analysis/`, `guide/`, `examples/README.md`):
   >   line-by-line md.

**Files:**
- Modify: `.claude/skills/layer-rules/references/layer-boundaries.md`.

**Done definition:**
- Surface map has 12 rows (was 10) covering every served outfacing path.
- No softener parentheticals on hand-authored md rows.
- Scanner-mode paragraph is present.

**Commit:** `docs(skill): close gaps in outfacing-doc surface map`

---

## Stage B — Lint extension (1-2 commits)

**Goal:** make `--lint` cover all four surfaces. Becomes the failing
test fixture for Stage D.

**Spec:**

1. **Add `lint_python_docstrings(paths: list[Path]) -> list[Violation]`**
   to `scripts/build_about_content.py`.
   - Parse each `.py` via `ast.parse()`.
   - Walk `Module`, `ClassDef`, `FunctionDef`, `AsyncFunctionDef`.
   - For each docstring node (`node.body[0]` when its `value` is an
     `ast.Constant` of type `str`), apply `LINT_PATTERN` and
     `CARVEOUT_PATTERN` line-by-line, using the docstring's
     `lineno`/`end_lineno` to compute correct file:line.
   - Returns the same `(path, line_no, line, matched_token)` shape as
     `lint_about_content`.
2. **Reuse `lint_about_content` for `examples/*.py` and `examples/README.md`**
   (line-by-line whole-file). Implementation is already correct — only
   the function name suggests "md", but it works on any line-based
   text. Optionally rename it to `lint_lines` and keep
   `lint_about_content` as a thin alias to preserve the existing test
   imports; not required.
3. **CLI dispatch in `--lint`** auto-routes by surface:
   - No positional args: scan
     - all rendered tool md (`skills/.../references/tools/*.md`),
     - all guide md (`skills/.../references/guide/*.md`),
     - all analysis md (`skills/.../references/analysis/*.md`),
     - `api/functions.py` (AST docstrings),
     - `examples/*.py` and `examples/README.md` (whole file).
   - Positional tool name: scope to that tool's md (existing behavior
     preserved).
   - Positional file path: route by extension/path:
     - `.md` → `lint_about_content`,
     - `api/functions.py` → `lint_python_docstrings`,
     - `examples/*.py` → `lint_about_content` (whole file).

**Tests:**

Per-surface parametrized tests so failures pinpoint the offending file
or function:

- `tests/unit/test_lint_about_content.py`:
  - Unit tests for `lint_python_docstrings`: catches §, today, Phase N,
    parent §, KG-XXX-NNN inside a sample docstring; ignores violations
    inside `# ...` comments; carveout for `[AQ]` / `[ENR]` lines;
    correct file:line reporting.
- `tests/unit/test_about_content.py`:
  - `test_about_content_lint_clean[<tool>]` (existing) — stays.
  - `test_guide_md_lint_clean[<file>]` (new) — parametrized over
    `guide/*.md`.
  - `test_analysis_md_lint_clean[<file>]` (new) — parametrized over
    `analysis/*.md`.
  - `test_examples_lint_clean[<file>]` (new) — parametrized over
    `examples/*.py` + `examples/README.md`.
  - `test_api_function_docstring_lint_clean[<fn>]` (new) — parametrized
    over `multiomics_explorer.__all__` (skips private helpers).

**Done definition:**
- New unit tests for `lint_python_docstrings` are green.
- The four new parametrized tests **fail today** in expected proportions
  (~50 api functions failing, ~26 metabolites.md, ~9 enrichment.md,
  ~3 derived_metrics.md, ~3 python_api.md, ~2 conventions.md,
  ~11 metabolites.py). The test list IS the work item for Stage D.
- Existing per-tool md test stays green.
- `uv run python scripts/build_about_content.py --lint` exits non-zero
  with bucket counts roughly matching the inventory above.

**Commit:** `feat(scripts): extend --lint to api docstrings + hand-authored md + examples` (and possibly a separate `test:` commit if the test additions are large).

---

## Stage C — Orchestrator skill updates (1 commit)

**Goal:** the `add-or-update-tool` skill's agent briefings already pass
`layer-rules` to all 4 implementers, so the surface map flows down. But
two specific agents need an extra reminder so they don't miss outfacing
on their owned surfaces.

**Spec:**

1. **`api-updater` brief addition** (in
   [.claude/skills/add-or-update-tool/SKILL.md](../../../.claude/skills/add-or-update-tool/SKILL.md)
   line 107 area or in the agent brief paragraph at line 109):
   > "Function docstrings on `api/functions.py` are agent-outfacing —
   > they reach Python users via `help()` and LLM agents via the
   > rendered md's 'Package import equivalent' path. The 9
   > outfacing-doc style rules apply with a Python-API audience accent
   > (dict keys, raised exceptions, return shape — not agent-routing
   > language). Run `--lint` after editing."

2. **`doc-updater` brief addition:**
   > "Analysis md (`references/analysis/*.md`) and example .py files
   > (`examples/*.py`) are agent-outfacing — they're served at
   > `docs://analysis/{name}` and `docs://examples/{file}`. The 9
   > outfacing-doc style rules apply (audience accent: analysis is
   > cross-tool methodology with biological precision; examples are
   > task-oriented runnable code where comments explain the pattern,
   > not biology lore). Run `--lint` after editing."

3. **Stage 3 step 1 cross-reference clarification.** Currently the
   text says "Mechanical backstop for the outfacing-doc style rules
   (rules 1-4 in the readability-pass spec — ISO dates, "today" counts,
   internal-history shorthand, `§` / `parent §`)." Add: "Now covers
   MCP md, api docstrings, hand-authored md (analysis + guide), and
   examples/*.py."

**Files:**
- Modify: `.claude/skills/add-or-update-tool/SKILL.md` (Phase 2 Stage 2
  agent brief area + Stage 3 step 1 text).

**Done definition:**
- Both agent briefs explicitly mention their outfacing surfaces and the
  9 rules (cross-link to spec, don't restate verbatim).
- Stage 3 step 1 text reflects expanded `--lint` coverage.
- No verbatim duplication of the 9 rules in this skill — they live in
  layer-rules + readability-pass spec.

**Commit:** `docs(skill): brief api-updater and doc-updater on their outfacing surfaces`

---

## Stage D — Cleanup sweeps

**Goal:** turn the failing parametrized tests from Stage B green by
fixing the underlying violations. One commit per surface — not bundled,
because each surface has a distinct audience accent (see below) and
splitting keeps diffs reviewable.

**D1 — `api/functions.py` docstrings** (the big one)

- ~50 public functions, ~100-300 violations expected.
- **Audience accent:** Python users + LLM agents on package-import.
  Lead with what the function returns (one-line dict-keys summary).
  Note `raises ValueError` / `raises Neo4jClientError` where relevant.
  Cross-link to MCP tool name only when the api function 1:1 mirrors
  a tool. Avoid agent-routing phrases ("drill into Y", "chain via Z") —
  those belong on the MCP surface.
- **Commit:** `docs(api): readability pass on api/functions.py docstrings`

**D2 — `analysis/*.md`** (medium)

- 38 violations across 3 files; 26 in `metabolites.md`.
- **Audience accent:** cross-tool analysis methodology. Biological
  precision matters (named compounds, exact pathway names). Drop
  internal-history shorthand and time-stamped counts — keep the
  biological caveats and the "permanent KG limitation" notes (those
  are the substance).
- **Commit:** `docs(analysis): readability pass on analysis md`

**D3 — `examples/*.py` + `examples/README.md`** (small)

- 11 violations; metabolites.py is the only `.py` with hits; README is
  unscanned but should be checked.
- **Audience accent:** task-oriented runnable code. Comments explain
  the *pattern* the example demonstrates, not the biology lore. Drop
  Phase N / KG release dates / audit refs from comments.
- **Commit:** `docs(examples): readability pass on examples`

**D4 — `guide/*.md`** (trivial)

- 5 violations; the 2026-05-07-era restructuring (commit `8d85962`)
  already covered most of this surface.
- **Audience accent:** cross-cutting preamble — terse, high-level.
- **Commit:** `docs(guide): drop residual shorthand from guide files`

**Done definition (per stage D commit):**
- The corresponding parametrized test goes green.
- `pytest tests/unit/ -q` clean.
- No behavior changes — if a doc surfaces that the *function* is wrong,
  fix the doc; do not silently retune what the function does.

**Done definition (Stage D overall):**
- `uv run python scripts/build_about_content.py --lint` exits 0.
- All four parametrized lint tests pass green.
- Spot-check 3 random function docstrings via `help(...)` from a Python
  REPL — they read user-facing, not as archaeology dumps.

---

## Cross-cutting

**Order:** A → B → C → D. Stage A grounds the truth (surface map);
Stage B builds the regression gate; Stage C makes the orchestrator
aware so the gate is enforced going forward; Stage D drives violations
to zero.

**Single commit per item** otherwise; mirrors the round-1 cadence.

**Verification loop after Stage D lands:**

1. `uv run python scripts/build_about_content.py --lint` — exit 0 across
   all 4 surfaces.
2. `pytest tests/unit/ -q` — all parametrized lint tests green.
3. Spot-read a guide page, an analysis page, an example .py file, and
   `help(gene_overview)` — they read clean to the intended audience
   (no internal-history shorthand, no archaeology).

---

## Out of scope

- `kg/queries_lib.py` docstrings — developer-internal per surface map;
  no audience-facing path.
- `mcp_server/tools.py` non-tool helper docstrings (`_conn`,
  `_group_by_organism`) — internal helpers, not on the package-import
  path. Folded in opportunistically only if Stage B's AST scan picks
  them up cleanly.
- Inline `# ...` Python comments in `api/functions.py` and
  `mcp_server/tools.py` — not outfacing per surface map. They DO
  contain shorthand and would benefit from a janitorial sweep, but
  that's separate work and not a readability rule.
- `CLAUDE.md` tool table — internal-team notes, not outfacing.
- Behavior changes anywhere. **No function semantics change.** Fix
  wrong docstrings; do not silently retune what the function does.

## Optional bonus

- Pre-commit hook wiring for `--lint` (still pending from round 1).
  Once round 2 lands, pre-commit catches all four surfaces in a single
  invocation.
- Janitorial sweep on inline `# ...` comments in `api/functions.py`.
  Not a readability-rule violation but would clean up developer-facing
  code paths that share the file with the outfacing docstrings.
