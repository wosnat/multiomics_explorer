# Outfacing-docs round 2 — design

End-to-end coverage of the four outfacing surfaces missed (or softened) by
round 1, plus the new `multiomics_explorer/analysis/*.py` docstring surface
not in any prior round. Single shared lint library; per-layer tests; cleanup
sweeps to drive all parametrized gates green.

Cross-refs:

- Round 1 spec: [2026-05-07-mcp-docs-readability-pass-design.md](2026-05-07-mcp-docs-readability-pass-design.md)
- Follow-up prompt: [../prompts/2026-05-08-outfacing-docs-round-2.md](../prompts/2026-05-08-outfacing-docs-round-2.md)
- Surface map: [../../../.claude/skills/layer-rules/references/layer-boundaries.md](../../../.claude/skills/layer-rules/references/layer-boundaries.md)

---

## Scope

**In:** extract the existing lint logic to a shared library, extend coverage
to api docstrings + analysis docstrings + hand-authored md (analysis + guide)
+ examples (.py + README.md), update orchestrator skills, and clean up all
violations the new tests surface.

**Out (carried from prompt):**
- Pre-commit hook wiring for `--lint` (optional bonus; can land separately).
- `kg/queries_lib.py` docstrings — developer-internal per surface map.
- `mcp_server/tools.py` non-tool helper docstrings (`_conn`, `_group_by_organism`)
  — internal helpers; folded in opportunistically only if the AST scan picks
  them up cleanly.
- Inline `# ...` comments in `api/functions.py` and `mcp_server/tools.py`
  — not outfacing per surface map.
- `CLAUDE.md` tool table — internal-team notes.
- Behavior changes anywhere. **No function semantics change.** Fix wrong
  docstrings; do not silently retune what the function does.

---

## Step ordering

| Step | What | Maps to prompt | Worktree state |
|---|---|---|---|
| 1 | Extract lint lib + add AST scanner + add 5 parametrized gates | Stage B | Tests red on the 5 new gates |
| 2 | Surface-map fix + orchestrator skill briefs | Stages A + C | Tests still red |
| 3 | Cleanup sweeps (D1-D5), one commit per surface | Stage D | Tests green; merge |

Single commit per logical unit. Step 1 is one commit (lib + tests are
coupled). Step 2 is two commits (one per skill file). Step 3 is five commits
(one per surface — each has a distinct audience accent, splitting keeps
diffs reviewable).

**Branch strategy:** all 3 steps on a worktree branch in
`.claude/worktrees/outfacing-docs-round-2/`. **Branch from local `main`**
(currently at `8abce76`) — local main is 6 commits ahead of `origin/main`,
and the slice depends on the local-only commits' state of the lint code and
surface map. Do not branch from `origin/main`. Merge to main only after
step 3 finishes and `pytest tests/unit/ -q` + `--lint` are both green.

---

## Architecture: lint library

**New file:** `multiomics_explorer/_outfacing_lint.py` (private — underscore
prefix = "internal API, don't import from user code").

**Public symbols:**

```python
LINT_PATTERN: re.Pattern        # the 9-rule regex (current contents, unchanged)
CARVEOUT_PATTERN: re.Pattern    # [AQ] / [ENR] drift markers

Violation = tuple[Path, int, str, str]   # (path, line_no, line, matched_token)

def lint_lines(paths: list[Path]) -> list[Violation]:
    """Line-by-line scan. Used for md, examples/*.py (whole file), README."""

def lint_python_docstrings(paths: list[Path]) -> list[Violation]:
    """AST-walk Module/ClassDef/FunctionDef/AsyncFunctionDef. Greedy —
    every docstring it sees, regardless of public/private. Caller narrows."""

def run_lint(paths: list[Path], stream: TextIO | None = None) -> int:
    """Print violations; return exit code (0 clean, 1 dirty)."""

# Back-compat alias for existing callers in tests:
lint_about_content = lint_lines
```

**AST line-number math.** For each docstring node, `ast.get_docstring(node, clean=False)`
returns the raw string; the docstring's source range is
`node.body[0].lineno` to `node.body[0].end_lineno`. Iterate
`splitlines()` of the raw docstring, offsetting line numbers from
`node.body[0].lineno`. That gives correct `file:line` reporting matching
what an editor jumps to.

**Carveout policy.** `CARVEOUT_PATTERN.search(line)` runs in both scanners.
Applies the same way in md, in `# ...` comments inside `examples/*.py`, and
inside Python docstrings — if a line contains `[AQ]` or `[ENR]`, that line
is exempt. Uniform across surfaces.

**Greedy AST walk.** The scanner walks every docstring it sees — module
docstring + every `def`/`async def` + every class. Public/private filtering
is the *caller's* concern (the test layer narrows by `__all__`). Bulk
`--lint` will catch shorthand in private helpers if any exists; that's a
feature, not a bug.

**What stays in the script.** `scripts/build_about_content.py` keeps the
`--lint` argparse and the dispatch logic (file-path → which scanner). It
imports from `_outfacing_lint`. The script gets ~80 lines smaller.

**CLI dispatch in `--lint`:**
- No positional args: scan all surfaces:
  - rendered tool md (`skills/.../references/tools/*.md`)
  - guide md (`skills/.../references/guide/*.md`)
  - analysis md (`skills/.../references/analysis/*.md`)
  - `api/functions.py` (AST docstrings)
  - `multiomics_explorer/analysis/*.py` (AST docstrings)
  - `examples/*.py` and `examples/README.md` (whole file)
- Positional tool name: scope to that tool's md (existing behavior preserved).
- Positional file path: route by extension/path:
  - `.md` → `lint_lines`
  - `api/functions.py` or `analysis/*.py` → `lint_python_docstrings`
  - `examples/*.py` → `lint_lines` (whole file)

---

## Step 1 — lint lib + tests

**File-level changes:**

| Change | File | Notes |
|---|---|---|
| New | `multiomics_explorer/_outfacing_lint.py` | Holds `LINT_PATTERN`, `CARVEOUT_PATTERN`, `lint_lines`, `lint_python_docstrings`, `run_lint`. Move from script. |
| Trim | `scripts/build_about_content.py` | Delete the lint definitions; import from `_outfacing_lint`. Keep `--lint` argparse + path-routing dispatch. Add path-routing for `api/functions.py`, `analysis/*.py`, `examples/*.py`. |
| Rename | `tests/unit/test_lint_about_content.py` → `tests/unit/test_outfacing_lint.py` | Replace `importlib.util.spec_from_file_location` dance with `from multiomics_explorer._outfacing_lint import ...`. Existing 17 tests stay green via the `lint_about_content = lint_lines` alias. |
| Extend | `tests/unit/test_outfacing_lint.py` | Add ~6-8 new units for `lint_python_docstrings`: catches §, today, Phase N, parent §, KG-XXX-NNN inside a sample docstring; ignores violations inside `# ...` comments outside docstrings; carveout for `[AQ]` / `[ENR]` lines; correct file:line reporting (docstring offset math). |
| Extend | `tests/unit/test_api_functions.py` | Add `test_api_function_docstring_lint_clean[<fn>]` parametrized over `multiomics_explorer.__all__`. Per-function: load `api/functions.py` once, slice violations to the function's `lineno`/`end_lineno` range, assert empty. |
| Extend | `tests/unit/test_analysis_about_content.py` | Add (a) `test_analysis_md_lint_clean[<file>]` parametrized over `analysis/*.md` glob, and (b) `test_analysis_function_docstring_lint_clean[<fn>]` parametrized over `multiomics_explorer.analysis.__all__` (3 IDs today: `response_matrix`, `gene_set_compare`, `to_dataframe`). |
| New | `tests/unit/test_guide_about_content.py` | `test_guide_md_lint_clean[<file>]` parametrized over `guide/*.md` glob. |
| New | `tests/unit/test_examples_about_content.py` | `test_examples_lint_clean[<file>]` parametrized over `examples/*.py` + `examples/README.md`. |

**Test-placement rule:** tests live with the layer that owns the source.
- API layer (`api/functions.py`) → `test_api_functions.py`.
- Analysis layer (analysis md + `analysis/*.py` docstrings) → `test_analysis_about_content.py`.
- MCP layer (rendered tool md, guide md, examples) → `test_about_content.py`,
  `test_guide_about_content.py`, `test_examples_about_content.py`.
- Lint library itself → `test_outfacing_lint.py`.

**Parametrize granularity:**
- Per-function for both Python-API surfaces (`api/functions.py`,
  `analysis/*.py`). During cleanup you can see "9 of 50 functions still
  dirty" in the test report; green-checks accumulate visibly.
- Per-file for md and examples — those surfaces are one file = one logical
  unit already.

**Implementation order within step 1** (one commit, but logical order matters):

1. Create `_outfacing_lint.py`, move lint code from script, add `lint_python_docstrings`.
2. Rename `test_lint_about_content.py` → `test_outfacing_lint.py`; switch imports; verify existing 17 tests pass.
3. Add new units for `lint_python_docstrings` in `test_outfacing_lint.py`. Verify pass.
4. Trim the script; verify CLI `--lint` (no args) sweeps all surfaces.
5. Add the 5 new parametrized gates in their layer-appropriate test files.
6. Run `pytest tests/unit/ -q` — confirm new gates fail in expected proportions; everything else green.

**Step 1 commit message:** `feat: extract outfacing-doc lint lib + extend coverage to api/analysis/examples/hand-authored md`.

**Failing test bucket sizes after step 1** (from prompt's inventory; analysis-py TBD):

- `test_api_function_docstring_lint_clean[*]`: ~50 IDs failing (~100-300 violations across them)
- `test_analysis_function_docstring_lint_clean[*]`: 3 IDs (count TBD — discovered when sweep runs)
- `test_analysis_md_lint_clean[*]`: 3 IDs failing (38 violations: 26 + 9 + 3)
- `test_guide_md_lint_clean[*]`: 2 IDs failing (5 violations: 3 + 2)
- `test_examples_lint_clean[*]`: 1 ID failing (11 violations in `metabolites.py`)

---

## Step 2 — surface map + skill briefs

**Two files, two commits. Use the `skill-creator` skill** for both —
skill-creator's voice/structure discipline applies to skill files.

### Commit 2.1 — `docs(skill): close gaps in outfacing-doc surface map`

**File:** `.claude/skills/layer-rules/references/layer-boundaries.md` (table at lines 416-427).

**Changes (5 edits):**

1. Add row for `examples/*.py`:
   > `examples/*.py` | **Yes** — served at `docs://examples/{file}`; agents read whole file | Yes (whole-file scan: comments ARE outfacing here)

2. Add row for `examples/README.md`:
   > `examples/README.md` | **Yes** — served at `docs://examples/{file}` | Yes

3. Add row for `multiomics_explorer/analysis/*.py` docstrings:
   > `multiomics_explorer/analysis/*.py` docstrings | **Yes** — Python API users (`help(response_matrix)`) and LLM agents via the rendered analysis md | Yes (Python-API audience accent — same as `api/functions.py`)

4. Drop softener on guide row: `Yes (rare edits)` → `Yes`.
5. Drop softener on analysis row: `Yes (best-effort)` → `Yes`.

**Add "Scanner notes" paragraph below the table:**

> **Scanner notes (lint mode per surface):**
> - Tool docstring + Pydantic `Field(description=...)`: caught indirectly via the rendered tool-md scan.
> - `api/functions.py` and `multiomics_explorer/analysis/*.py` docstrings: AST-extracted; `# ...` comments are not scanned (per the surface-map row above).
> - `examples/*.py`: whole file scanned line-by-line — comments ARE outfacing here, since the file IS the artifact.
> - Hand-authored md (`analysis/`, `guide/`, `examples/README.md`): line-by-line.

**Done definition:** table has 13 rows (was 10), no softener parentheticals
on hand-authored md rows, scanner-notes paragraph present.

### Commit 2.2 — `docs(skill): brief api-updater and doc-updater on their outfacing surfaces`

**File:** `.claude/skills/add-or-update-tool/SKILL.md`.

**Three edits** — terse cross-references, not verbatim duplication of the 9 rules:

1. **`api-updater` agent brief addition.** Paragraph in the implementer's
   brief stating that `api/functions.py` and `multiomics_explorer/analysis/*.py`
   docstrings are agent-outfacing (Python users via `help()` + LLM agents
   via the rendered md's "Package import equivalent" + the analysis md).
   The 9 rules apply with Python-API audience accent (dict keys, raised
   exceptions, return shape — not agent-routing language). Run `--lint`
   after editing.

2. **`doc-updater` agent brief addition.** Analysis md
   (`references/analysis/*.md`) and example .py files (`examples/*.py`)
   are agent-outfacing — served at `docs://analysis/{name}` and
   `docs://examples/{file}`. The 9 rules apply, audience accent: analysis
   = cross-tool methodology with biological precision; examples =
   task-oriented runnable code where comments explain the pattern, not
   biology lore. Run `--lint` after editing.

3. **Stage 3 step 1 cross-reference clarification.** Existing line about
   "mechanical backstop for outfacing-doc style rules" gets a coverage
   update: "Now covers MCP md, api docstrings, analysis docstrings,
   hand-authored md (analysis + guide), and `examples/*.py`."

**Done definition:** both agent briefs explicitly call out their outfacing
surfaces and link to the 9 rules; Stage 3 step 1 reflects expanded
`--lint` coverage; no verbatim restating of the 9 rules in this skill.

**No code changes** in this step. Tests still red on the 5 new gates —
fixed in step 3.

---

## Step 3 — cleanup sweeps

Five commits, one per surface, ordered cheapest-to-priciest so easy wins
land first.

### D4 first — `docs(guide): drop residual shorthand from guide files`
- 5 violations across 2 files (`python_api.md`: 3, `conventions.md`: 2).
- Most of guide was already cleaned in commit `8d85962`.
- **Test that goes green:** `test_guide_md_lint_clean[*]` (both IDs).

### D3 — `docs(examples): readability pass on examples`
- 11 violations in `examples/metabolites.py`. README probably clean (1-min
  scan to confirm).
- Audience accent: **task-oriented runnable code**. Comments explain the
  *pattern* the example demonstrates, not biology lore. Drop Phase N / KG
  release dates / audit refs from comments.
- **Test that goes green:** `test_examples_lint_clean[*]`.

### D2 — `docs(analysis): readability pass on analysis md`
- 38 violations across 3 files; 26 in `metabolites.md` is the dense one
  (`Part 4 §4.1.1`, `audit §4.1.2`, `Phase 2`, `KG-A5`, `KG-MET-011`,
  `KG release 2026-05-05`, `§b2`, `§g`).
- Audience accent: **cross-tool analysis methodology with biological
  precision**. Drop internal-history shorthand and time-stamped counts.
  **Keep** the biological caveats and "permanent KG limitation" notes —
  those are substance.
- **Test that goes green:** `test_analysis_md_lint_clean[*]`.

### D5 — `docs(analysis-py): readability pass on analysis function docstrings`
- 3 functions in `__all__` (`response_matrix`, `gene_set_compare`,
  `to_dataframe`); plus other public-named functions (`fisher_ora`,
  `de_enrichment_inputs`, `cluster_enrichment_inputs`) caught by the bulk
  `--lint` sweep but without their own per-function test ID.
- Audience accent: **Python users + LLM agents on package-import**.
  Same accent as D1. Lead with what the function returns; note raised
  exceptions; avoid agent-routing phrases.
- Bucket size TBD — discovered during step 1.
- **Test that goes green:** `test_analysis_function_docstring_lint_clean[*]`.

### D1 last — `docs(api): readability pass on api/functions.py docstrings`
- ~50 functions, ~100-300 violations expected. The big one.
- Audience accent: **Python users + LLM agents on package-import**. Lead
  with what the function returns (one-line dict-keys summary). Note
  `raises ValueError` / `raises Neo4jClientError` where relevant.
  Cross-link to MCP tool name only when the api function 1:1 mirrors a
  tool. Avoid agent-routing phrases ("drill into Y", "chain via Z") —
  those belong on the MCP surface.
- **Test that goes green:** `test_api_function_docstring_lint_clean[*]`
  (~50 IDs).

**Done definition (per D commit):** corresponding parametrized test goes
green; `pytest tests/unit/ -q` clean against everything else; **no
behavior changes** — if a docstring surfaces that the *function* is
wrong, fix the doc, do not silently retune what the function does.

**Done definition (step 3 overall):**
- `uv run python scripts/build_about_content.py --lint` exits 0.
- All 5 parametrized lint tests pass green.
- Spot-check 3 random function docstrings via `help(...)` from a Python
  REPL — they read user-facing, not as archaeology dumps.
- Then merge worktree → main.

---

## Verification

**Step-1 acceptance signal (worktree, post-commit):**
- `pytest tests/unit/test_outfacing_lint.py -q` — green (library units pass).
- `pytest tests/unit/ -q` — red on the 5 new parametrized gates only.
- `uv run python scripts/build_about_content.py --lint` — exits non-zero
  with bucket counts in the same proportions as the inventory above.

**Step-2 acceptance signal:** no test changes (still red on the 5 surfaces).
Manual check: open `layer-boundaries.md` → 13 rows, no softeners,
scanner-notes paragraph present. Open `add-or-update-tool/SKILL.md` →
api-updater + doc-updater briefs name their outfacing surfaces; Stage 3
step 1 reflects expanded `--lint`.

**Step-3 acceptance signal (per D-commit):** corresponding parametrized
test goes green; nothing else regresses.

**Final verification before merge:**

1. `uv run python scripts/build_about_content.py --lint` — exit 0 across all surfaces.
2. `pytest tests/unit/ -q` — all parametrized lint tests green.
3. Spot-read: a guide page, an analysis md page, an analysis function
   docstring (`help(response_matrix)`), an example .py file,
   `help(gene_overview)` — they read clean to the intended audience (no
   archaeology, no internal-history shorthand).

---

## Cross-cutting

**Single commit per logical unit.** Mirrors round-1 cadence.

**No verbatim duplication of the 9 rules** in skill files — they live in
`layer-rules` + the round-1 readability-pass spec. Skill briefs cross-link.

**Carveout `[AQ]`/`[ENR]` is uniform across all surfaces.** A docstring
genuinely needing a drift-marker tag is allowed; spot-review whether the
tag is appropriate during cleanup.

**No behavior changes anywhere.** Repeated. Load-bearing.
