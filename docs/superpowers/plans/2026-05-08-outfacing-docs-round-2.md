# Outfacing-docs round 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend outfacing-doc lint coverage to api docstrings, analysis docstrings, hand-authored md (analysis + guide), and examples (.py + README), via a shared lint library; clean up all violations the new tests surface.

**Architecture:** Extract `LINT_PATTERN`/`CARVEOUT_PATTERN`/`lint_lines`/`run_lint` from `scripts/build_about_content.py` into a private module `multiomics_explorer/_outfacing_lint.py`; add a new `lint_python_docstrings` AST scanner in the same module; add 5 parametrized lint gates in layer-colocated test files; clean violations with audience-accent-respecting commits (one per surface).

**Tech Stack:** Python (pytest, ast module), existing pytest parametrize patterns, fastmcp.

**Spec:** [docs/superpowers/specs/2026-05-08-outfacing-docs-round-2-design.md](../specs/2026-05-08-outfacing-docs-round-2-design.md)

---

## File Structure

**New files:**
- `multiomics_explorer/_outfacing_lint.py` — shared lint library (private module).
- `tests/unit/test_guide_about_content.py` — guide md lint gate.
- `tests/unit/test_examples_about_content.py` — examples lint gate.

**Renamed:**
- `tests/unit/test_lint_about_content.py` → `tests/unit/test_outfacing_lint.py` (keeps existing 17 unit tests; absorbs new AST-scanner units).

**Modified:**
- `scripts/build_about_content.py` — trim lint code; import from `_outfacing_lint`; extend CLI dispatch to all surfaces.
- `tests/unit/test_api_functions.py` — add `test_api_function_docstring_lint_clean[<fn>]`.
- `tests/unit/test_analysis_about_content.py` — add `test_analysis_md_lint_clean[<file>]` + `test_analysis_function_docstring_lint_clean[<fn>]`.
- `.claude/skills/layer-rules/references/layer-boundaries.md` — surface map fix.
- `.claude/skills/add-or-update-tool/SKILL.md` — agent brief additions.
- 5 cleanup-target surfaces (step 3) — see Tasks 12-16.

---

## Worktree setup (preflight)

Before any task: ensure you're operating inside a worktree at `.claude/worktrees/outfacing-docs-round-2/`, branched from **local** `main` (not `origin/main`). Use `superpowers:using-git-worktrees` to set this up at execution start. The branch is `outfacing-docs-round-2`. All commits in this plan happen on that branch; merge to main only after Task 17 verification.

---

## Task 1: Create shared lint library skeleton

**Files:**
- Create: `multiomics_explorer/_outfacing_lint.py`

- [ ] **Step 1: Create the new private module with imports + regexes**

Write `multiomics_explorer/_outfacing_lint.py`:

```python
"""Outfacing-doc style-rule lint scanners.

Private module. Used by scripts/build_about_content.py CLI and by the
parametrized lint gates in tests/unit/. The 9 outfacing-doc style rules
are documented in docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import TextIO

# Non-exhaustive by design - encodes shorthand patterns observed in the
# readability-pass deletions. Extension contract: when reviewer or author
# spots a recurring stale-language pattern this regex did NOT catch, add
# a pattern here and a unit test in tests/unit/test_outfacing_lint.py
# in the same PR.
LINT_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}"     # ISO date stamp
    r"| today\b"              # stale "today" count
    r"|Phase [0-9]"           # internal phase tag
    r"|§"                     # cross-ref shorthand
    r"|\baudit\b"             # internal audit ref
    r"|KG-[A-Z]+-[0-9]"       # KG-XXX-NNN ticket ID
    r"|Mode-[A-Z]\b"          # Mode-A / Mode-B template tag
    r"|Cluster [A-Z]\b"       # Cluster A / Cluster B internal tag
    r"|parent §"              # cross-ref shorthand
)

# Drift-marker carveout. The [AQ] (annotation_quality redefinition) and
# [ENR] (informative_only=True default flip) markers stay as 1-line inline
# notes on affected tools.
CARVEOUT_PATTERN = re.compile(r"\[AQ\]|\[ENR\]")

Violation = tuple[Path, int, str, str]


def lint_lines(paths: list[Path]) -> list[Violation]:
    """Line-by-line scan. Used for md, examples/*.py (whole file), README.

    Returns ``(path, line_no, line, matched_token)`` per violation.
    Lines containing ``[AQ]`` / ``[ENR]`` drift markers are exempt.
    """
    violations: list[Violation] = []
    for path in paths:
        try:
            text = path.read_text()
        except OSError as e:
            print(f"  SKIP {path}: {e}", file=sys.stderr)
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if CARVEOUT_PATTERN.search(line):
                continue
            m = LINT_PATTERN.search(line)
            if m:
                violations.append((path, i, line, m.group(0)))
    return violations


# Back-compat alias for callers prior to the rename.
lint_about_content = lint_lines


def lint_python_docstrings(paths: list[Path]) -> list[Violation]:
    """AST-walk Module/ClassDef/FunctionDef/AsyncFunctionDef and lint
    every docstring found. Greedy - public/private filtering is the
    caller's concern.

    Returns ``(path, line_no, line, matched_token)`` per violation, with
    line numbers anchored to the source file (not docstring-relative).
    """
    violations: list[Violation] = []
    for path in paths:
        try:
            text = path.read_text()
        except OSError as e:
            print(f"  SKIP {path}: {e}", file=sys.stderr)
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as e:
            print(f"  SKIP {path}: {e}", file=sys.stderr)
            continue
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            if not (node.body and isinstance(node.body[0], ast.Expr)):
                continue
            doc_node = node.body[0]
            if not (
                isinstance(doc_node.value, ast.Constant)
                and isinstance(doc_node.value.value, str)
            ):
                continue
            doc_start_line = doc_node.lineno
            for offset, line in enumerate(doc_node.value.value.splitlines()):
                if CARVEOUT_PATTERN.search(line):
                    continue
                m = LINT_PATTERN.search(line)
                if m:
                    violations.append(
                        (path, doc_start_line + offset, line, m.group(0))
                    )
    return violations


def run_lint(paths: list[Path], stream: TextIO | None = None) -> int:
    """Print violations and return a process exit code (0 clean, 1 dirty).

    Routes per path: ``.md`` and ``examples/`` paths use ``lint_lines``;
    ``api/functions.py`` and ``multiomics_explorer/analysis/*.py`` paths
    use ``lint_python_docstrings``.
    """
    if stream is None:
        stream = sys.stdout
    md_or_examples: list[Path] = []
    py_docstring: list[Path] = []
    for p in paths:
        if p.suffix == ".md":
            md_or_examples.append(p)
        elif "examples" in p.parts:
            md_or_examples.append(p)
        elif p.suffix == ".py":
            py_docstring.append(p)
        else:
            md_or_examples.append(p)
    violations = lint_lines(md_or_examples) + lint_python_docstrings(py_docstring)
    cwd = Path.cwd()
    for path, line_no, line, token in violations:
        try:
            shown = path.relative_to(cwd)
        except ValueError:
            shown = path
        print(f"{shown}:{line_no}: {token!r} in: {line.strip()}", file=stream)
    if violations:
        files = len({v[0] for v in violations})
        print(
            f"\n{len(violations)} violation(s) across {files} file(s).",
            file=stream,
        )
        print(
            "See docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md "
            "for the 9 outfacing-doc style rules.",
            file=stream,
        )
        return 1
    print("Lint clean.", file=stream)
    return 0
```

- [ ] **Step 2: Sanity-check the module imports clean**

Run: `uv run python -c "from multiomics_explorer._outfacing_lint import lint_lines, lint_python_docstrings, run_lint, LINT_PATTERN, CARVEOUT_PATTERN; print('ok')"`
Expected: `ok`

- [ ] **Step 3: No commit yet** — Task 2 renames the existing test file to use this module before any commit.

---

## Task 2: Rename existing lint test file and switch imports

**Files:**
- Rename: `tests/unit/test_lint_about_content.py` → `tests/unit/test_outfacing_lint.py`
- Modify: import block in the renamed file

- [ ] **Step 1: Rename the file**

Run: `git mv tests/unit/test_lint_about_content.py tests/unit/test_outfacing_lint.py`

- [ ] **Step 2: Replace the `_load_module()` dance with a normal import**

In `tests/unit/test_outfacing_lint.py`, find the top of file (lines ~10-30):

```python
import importlib.util
import io
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "build_about_content.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_about_content", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lint_mod():
    return _load_module()
```

Replace with:

```python
import io
from pathlib import Path

import pytest

from multiomics_explorer import _outfacing_lint as lint_mod_real


@pytest.fixture(scope="module")
def lint_mod():
    return lint_mod_real
```

Leave the rest of the file (the 17 existing tests) unchanged — they reference `lint_mod.lint_about_content`, which still works via the back-compat alias.

- [ ] **Step 3: Run the existing tests**

Run: `pytest tests/unit/test_outfacing_lint.py -q`
Expected: 17 passed.

- [ ] **Step 4: No commit yet** — Task 3 adds the new units before the first commit.

---

## Task 3: Add unit tests for `lint_python_docstrings`

**Files:**
- Modify: `tests/unit/test_outfacing_lint.py` (append new tests at end)

- [ ] **Step 1: Append unit tests**

At the end of `tests/unit/test_outfacing_lint.py`, append:

```python


# ---------------------------------------------------------------------------
# lint_python_docstrings — AST scanner for .py files
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, body: str) -> Path:
    f = tmp_path / "sample.py"
    f.write_text(body)
    return f


def test_python_docstrings_function_exists(lint_mod):
    assert hasattr(lint_mod, "lint_python_docstrings")


def test_python_docstrings_catches_iso_date(lint_mod, tmp_path):
    f = _write_py(
        tmp_path,
        'def foo():\n    """Returns gene rows. Updated 2026-05-08."""\n    pass\n',
    )
    vs = lint_mod.lint_python_docstrings([f])
    assert len(vs) == 1
    assert vs[0][1] == 2  # docstring line in source
    assert vs[0][3] == "2026-05-08"


def test_python_docstrings_catches_section_marker(lint_mod, tmp_path):
    f = _write_py(
        tmp_path,
        'def foo():\n    """Returns rows.\n\n    See parent §10 for details.\n    """\n    pass\n',
    )
    vs = lint_mod.lint_python_docstrings([f])
    assert len(vs) >= 1
    assert any("§" in v[3] for v in vs)


def test_python_docstrings_catches_phase_tag(lint_mod, tmp_path):
    f = _write_py(
        tmp_path,
        'def foo():\n    """Renamed in Phase 2."""\n    pass\n',
    )
    vs = lint_mod.lint_python_docstrings([f])
    assert len(vs) == 1


def test_python_docstrings_catches_kg_ticket(lint_mod, tmp_path):
    f = _write_py(
        tmp_path,
        'def foo():\n    """Pending KG-MET-002 backfill."""\n    pass\n',
    )
    vs = lint_mod.lint_python_docstrings([f])
    assert len(vs) == 1


def test_python_docstrings_carveout_aq_marker(lint_mod, tmp_path):
    f = _write_py(
        tmp_path,
        'def foo():\n    """[AQ] redefined 2026-05-01: annotation_state encoding."""\n    pass\n',
    )
    vs = lint_mod.lint_python_docstrings([f])
    assert vs == []


def test_python_docstrings_ignores_inline_comments(lint_mod, tmp_path):
    """Inline `# ...` comments are NOT scanned per the surface map.

    Even if a comment contains shorthand like ``# Phase 2 cleanup``, the
    scanner sees only the AST docstring node, not the source comments.
    """
    f = _write_py(
        tmp_path,
        '# Phase 2 cleanup pending\n# 2026-05-08 audit\ndef foo():\n    """Plain prose."""\n    pass\n',
    )
    vs = lint_mod.lint_python_docstrings([f])
    assert vs == []


def test_python_docstrings_walks_module_class_function(lint_mod, tmp_path):
    """Greedy walk: module docstring + class + function all scanned."""
    body = (
        '"""Module docstring with §1 shorthand."""\n'
        '\n'
        'class C:\n'
        '    """Class docstring with Phase 2 tag."""\n'
        '\n'
        '    def m(self):\n'
        '        """Method docstring with KG-XYZ-001 ticket."""\n'
        '        pass\n'
    )
    f = _write_py(tmp_path, body)
    vs = lint_mod.lint_python_docstrings([f])
    tokens = sorted(v[3] for v in vs)
    assert tokens == ["KG-XYZ-001", "Phase 2", "§"]


def test_python_docstrings_correct_file_line(lint_mod, tmp_path):
    """File:line reporting must point to the line in the source file."""
    f = _write_py(
        tmp_path,
        'def foo():\n    pass\n\n\ndef bar():\n    """Has 2026-05-08 in it."""\n    pass\n',
    )
    vs = lint_mod.lint_python_docstrings([f])
    assert len(vs) == 1
    assert vs[0][0] == f
    assert vs[0][1] == 6  # docstring is on line 6 of the source


def test_python_docstrings_skips_files_without_docstrings(lint_mod, tmp_path):
    f = _write_py(tmp_path, 'def foo():\n    return 1\n')
    vs = lint_mod.lint_python_docstrings([f])
    assert vs == []
```

- [ ] **Step 2: Run the new units**

Run: `pytest tests/unit/test_outfacing_lint.py -q`
Expected: 27 passed (17 existing + 10 new).

- [ ] **Step 3: No commit yet** — Task 4 trims the script before the first commit.

---

## Task 4: Trim the build script to import from the new module

**Files:**
- Modify: `scripts/build_about_content.py` (lines ~485-565)

- [ ] **Step 1: Find the lint block in the script**

Run: `grep -n "LINT_PATTERN\|CARVEOUT_PATTERN\|def lint_about_content\|def run_lint" scripts/build_about_content.py`
Expected: lines around 492, 513, 516, 540.

- [ ] **Step 2: Replace the lint block with an import**

In `scripts/build_about_content.py`, delete the block from the `LINT_PATTERN = re.compile(` definition through the end of `def run_lint(...)` (roughly lines 486-565 — confirm with grep). Replace it with a single import line near the top of the file, alongside the existing imports:

```python
from multiomics_explorer._outfacing_lint import (
    LINT_PATTERN,
    CARVEOUT_PATTERN,
    lint_about_content,
    lint_lines,
    lint_python_docstrings,
    run_lint,
)
```

(Keep `LINT_PATTERN`/`CARVEOUT_PATTERN`/`lint_about_content` in the import list even if the script doesn't use them — the existing imports preserve back-compat for any callers expecting them.)

- [ ] **Step 3: Extend CLI dispatch in `--lint`**

Find the `if args.lint:` block in `main()` (around lines 607-620). Currently it only globs `OUTPUT_DIR/*.md`. Replace it with a sweep that covers all surfaces:

```python
    if args.lint:
        if args.tools:
            paths: list[Path] = []
            for name in args.tools:
                p = Path(name)
                if p.exists():
                    paths.append(p)
                else:
                    md_path = OUTPUT_DIR / f"{name}.md"
                    if not md_path.exists():
                        print(f"Error: '{name}' is neither a file nor a registered tool md", file=sys.stderr)
                        sys.exit(2)
                    paths.append(md_path)
        else:
            repo_root = Path(__file__).resolve().parent.parent
            skills_refs = repo_root / "multiomics_explorer" / "skills" / "multiomics-kg-guide" / "references"
            paths = (
                sorted(OUTPUT_DIR.glob("*.md"))
                + sorted((skills_refs / "guide").glob("*.md"))
                + sorted((skills_refs / "analysis").glob("*.md"))
                + [repo_root / "multiomics_explorer" / "api" / "functions.py"]
                + sorted((repo_root / "multiomics_explorer" / "analysis").glob("*.py"))
                + sorted((repo_root / "examples").glob("*.py"))
                + [repo_root / "examples" / "README.md"]
            )
            paths = [p for p in paths if p.exists()]
            if not paths:
                print(f"Error: no scannable files found", file=sys.stderr)
                sys.exit(2)
        sys.exit(run_lint(paths))
```

- [ ] **Step 4: Confirm script still parses**

Run: `uv run python scripts/build_about_content.py --help`
Expected: Help text printed; no import errors.

- [ ] **Step 5: Confirm scoped tool-name lint still works**

Run: `uv run python scripts/build_about_content.py --lint gene_overview`
Expected: Either "Lint clean." (exit 0) or violations listed (exit 1) — both prove the tool-name scoping path works.

- [ ] **Step 6: Confirm no-args lint sweeps all surfaces**

Run: `uv run python scripts/build_about_content.py --lint 2>&1 | tail -20`
Expected: Many violations across `api/functions.py`, `examples/metabolites.py`, analysis md files, guide md files, and possibly `analysis/*.py`. The summary line should mention violations in multiple files.

- [ ] **Step 7: No commit yet** — Tasks 5-9 add the parametrized gates before the first commit.

---

## Task 5: Add per-function api docstring lint gate

**Files:**
- Modify: `tests/unit/test_api_functions.py` (append new test class at end)

- [ ] **Step 1: Append the parametrized gate**

At the end of `tests/unit/test_api_functions.py`, append:

```python


# ---------------------------------------------------------------------------
# Outfacing-doc lint gate for api/functions.py docstrings
# ---------------------------------------------------------------------------
# See docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
# for the 9 style rules. Gate is per-function so cleanup progress is visible
# in the test report.

import ast
import inspect
from pathlib import Path

from multiomics_explorer._outfacing_lint import lint_python_docstrings

_API_FILE = Path(inspect.getsourcefile(api)).resolve()


def _api_public_function_names() -> list[str]:
    """Top-level public functions in api/functions.py via AST walk."""
    tree = ast.parse(_API_FILE.read_text())
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names


def _api_function_line_range(name: str) -> tuple[int, int]:
    """Line range of `name` in api/functions.py (1-indexed, inclusive)."""
    tree = ast.parse(_API_FILE.read_text())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node.lineno, node.end_lineno
    raise LookupError(f"function {name!r} not found in {_API_FILE}")


@pytest.mark.parametrize("fn_name", _api_public_function_names())
def test_api_function_docstring_lint_clean(fn_name: str):
    """Each public function in api/functions.py has a clean docstring."""
    start, end = _api_function_line_range(fn_name)
    violations = lint_python_docstrings([_API_FILE])
    fn_violations = [v for v in violations if start <= v[1] <= end]
    if fn_violations:
        msg_lines = [
            f"{fn_name} ({_API_FILE.name}:{start}-{end}) has outfacing-doc violations:",
        ]
        for path, line_no, line, token in fn_violations:
            msg_lines.append(f"  {path.name}:{line_no}: {token!r} in: {line.strip()}")
        pytest.fail("\n".join(msg_lines))
```

- [ ] **Step 2: Confirm test collects with ~50 IDs**

Run: `pytest tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean --collect-only -q | head -10`
Expected: Many lines like `tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean[gene_overview]` — ~40-50 IDs total.

- [ ] **Step 3: Confirm gate fails on existing violations**

Run: `pytest tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean -q 2>&1 | tail -5`
Expected: Many failures (exact count discovered here; prompt estimate ~50 IDs failing).

- [ ] **Step 4: No commit yet.**

---

## Task 6: Add analysis docstring + analysis md lint gates

**Files:**
- Modify: `tests/unit/test_analysis_about_content.py` (append at end)

- [ ] **Step 1: Append the gates**

At the end of `tests/unit/test_analysis_about_content.py`, append:

```python


# ---------------------------------------------------------------------------
# Outfacing-doc lint gates: analysis md + analysis function docstrings
# ---------------------------------------------------------------------------

import ast as _ast_for_lint
from multiomics_explorer._outfacing_lint import (
    lint_lines as _lint_lines,
    lint_python_docstrings as _lint_py,
)

_ANALYSIS_PKG_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "multiomics_explorer" / "analysis"
)


def _analysis_md_files() -> list[Path]:
    return sorted(ABOUT_DIR.glob("*.md"))


def _analysis_public_functions() -> list[tuple[str, Path, int, int]]:
    """Top-level public functions across analysis/*.py.

    Returns (name, source_file, start_line, end_line) tuples.
    """
    out = []
    for py_file in sorted(_ANALYSIS_PKG_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        tree = _ast_for_lint.parse(py_file.read_text())
        for node in tree.body:
            if isinstance(node, (_ast_for_lint.FunctionDef, _ast_for_lint.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    out.append((node.name, py_file, node.lineno, node.end_lineno))
    return out


@pytest.mark.parametrize(
    "md_path",
    _analysis_md_files(),
    ids=lambda p: p.stem,
)
def test_analysis_md_lint_clean(md_path: Path):
    violations = _lint_lines([md_path])
    if violations:
        msg_lines = [f"{md_path.name} has outfacing-doc violations:"]
        for path, line_no, line, token in violations:
            msg_lines.append(f"  {path.name}:{line_no}: {token!r} in: {line.strip()}")
        pytest.fail("\n".join(msg_lines))


@pytest.mark.parametrize(
    "spec",
    _analysis_public_functions(),
    ids=lambda spec: f"{spec[1].stem}.{spec[0]}",
)
def test_analysis_function_docstring_lint_clean(spec):
    name, src_file, start, end = spec
    violations = _lint_py([src_file])
    fn_violations = [v for v in violations if start <= v[1] <= end]
    if fn_violations:
        msg_lines = [
            f"{name} ({src_file.name}:{start}-{end}) has outfacing-doc violations:",
        ]
        for path, line_no, line, token in fn_violations:
            msg_lines.append(f"  {path.name}:{line_no}: {token!r} in: {line.strip()}")
        pytest.fail("\n".join(msg_lines))
```

- [ ] **Step 2: Confirm collection**

Run: `pytest tests/unit/test_analysis_about_content.py::test_analysis_md_lint_clean tests/unit/test_analysis_about_content.py::test_analysis_function_docstring_lint_clean --collect-only -q | head -20`
Expected: 3 IDs for md (`derived_metrics`, `enrichment`, `metabolites`) + multiple IDs for analysis functions (`expression.response_matrix`, etc.).

- [ ] **Step 3: Confirm gates fail as expected**

Run: `pytest tests/unit/test_analysis_about_content.py -q 2>&1 | tail -5`
Expected: All 3 md IDs fail; some analysis function IDs fail (count discovered here).

- [ ] **Step 4: No commit yet.**

---

## Task 7: Create guide md lint gate

**Files:**
- Create: `tests/unit/test_guide_about_content.py`

- [ ] **Step 1: Write the new file**

Create `tests/unit/test_guide_about_content.py`:

```python
"""Outfacing-doc lint gate for hand-authored guide md.

Files at multiomics_explorer/skills/multiomics-kg-guide/references/guide/*.md
are served at docs://guide/{name}. Style rules from
docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md apply.
"""

from pathlib import Path

import pytest

from multiomics_explorer._outfacing_lint import lint_lines

GUIDE_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "multiomics_explorer" / "skills" / "multiomics-kg-guide" / "references" / "guide"
)


def _guide_md_files() -> list[Path]:
    if not GUIDE_DIR.exists():
        return []
    return sorted(GUIDE_DIR.glob("*.md"))


@pytest.mark.parametrize(
    "md_path",
    _guide_md_files(),
    ids=lambda p: p.stem,
)
def test_guide_md_lint_clean(md_path: Path):
    violations = lint_lines([md_path])
    if violations:
        msg_lines = [f"{md_path.name} has outfacing-doc violations:"]
        for path, line_no, line, token in violations:
            msg_lines.append(f"  {path.name}:{line_no}: {token!r} in: {line.strip()}")
        pytest.fail("\n".join(msg_lines))
```

- [ ] **Step 2: Confirm collection**

Run: `pytest tests/unit/test_guide_about_content.py --collect-only -q`
Expected: 4 IDs (`concepts`, `conventions`, `python_api`, `start_here`).

- [ ] **Step 3: Confirm gate fails as expected**

Run: `pytest tests/unit/test_guide_about_content.py -q 2>&1 | tail -5`
Expected: 2 IDs fail (`python_api`, `conventions`); 2 pass (`concepts`, `start_here`).

- [ ] **Step 4: No commit yet.**

---

## Task 8: Create examples lint gate

**Files:**
- Create: `tests/unit/test_examples_about_content.py`

- [ ] **Step 1: Write the new file**

Create `tests/unit/test_examples_about_content.py`:

```python
"""Outfacing-doc lint gate for examples/ (whole-file scan).

Files at examples/*.py and examples/README.md are served at
docs://examples/{file}. The whole file is read by agents (the file IS
the runnable artifact), so comments ARE outfacing here. Style rules
from docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
apply line-by-line.
"""

from pathlib import Path

import pytest

from multiomics_explorer._outfacing_lint import lint_lines

EXAMPLES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "examples"
)


def _examples_files() -> list[Path]:
    if not EXAMPLES_DIR.exists():
        return []
    py_files = sorted(EXAMPLES_DIR.glob("*.py"))
    md_files = sorted(EXAMPLES_DIR.glob("*.md"))
    return py_files + md_files


@pytest.mark.parametrize(
    "path",
    _examples_files(),
    ids=lambda p: p.name,
)
def test_examples_lint_clean(path: Path):
    violations = lint_lines([path])
    if violations:
        msg_lines = [f"{path.name} has outfacing-doc violations:"]
        for p, line_no, line, token in violations:
            msg_lines.append(f"  {p.name}:{line_no}: {token!r} in: {line.strip()}")
        pytest.fail("\n".join(msg_lines))
```

- [ ] **Step 2: Confirm collection**

Run: `pytest tests/unit/test_examples_about_content.py --collect-only -q`
Expected: At least `metabolites.py`, `pathway_enrichment.py`, `README.md` (3+ IDs).

- [ ] **Step 3: Confirm gate fails as expected**

Run: `pytest tests/unit/test_examples_about_content.py -q 2>&1 | tail -5`
Expected: At least `metabolites.py` fails.

- [ ] **Step 4: No commit yet — Task 9 verifies the full picture before committing.**

---

## Task 9: Verify full step-1 picture and commit

- [ ] **Step 1: Run the full unit test suite**

Run: `pytest tests/unit/ -q 2>&1 | tail -20`
Expected:
- `test_outfacing_lint.py`: 27 passed.
- `test_api_function_docstring_lint_clean[*]`: many failures (~40-50 IDs).
- `test_analysis_md_lint_clean[*]`: 3 failures (`derived_metrics`, `enrichment`, `metabolites`).
- `test_analysis_function_docstring_lint_clean[*]`: some failures (count varies).
- `test_guide_md_lint_clean[*]`: 2 failures (`python_api`, `conventions`).
- `test_examples_lint_clean[*]`: at least `metabolites.py` fails.
- All other unit tests still pass.

If anything outside the 5 new gates fails, stop and fix — that's a regression.

- [ ] **Step 2: Run the lint CLI**

Run: `uv run python scripts/build_about_content.py --lint 2>&1 | tail -5`
Expected: `N violation(s) across M file(s).` summary; exit code 1.

- [ ] **Step 3: Stage and commit**

```bash
git add multiomics_explorer/_outfacing_lint.py
git add scripts/build_about_content.py
git add tests/unit/test_outfacing_lint.py
git add tests/unit/test_lint_about_content.py  # for the rename
git add tests/unit/test_api_functions.py
git add tests/unit/test_analysis_about_content.py
git add tests/unit/test_guide_about_content.py
git add tests/unit/test_examples_about_content.py
git status
```

Expected: rename of test_lint_about_content.py → test_outfacing_lint.py shown; modifications to script + api/analysis test files; new files for guide/examples test files; new private module.

```bash
git commit -m "$(cat <<'EOF'
feat: extract outfacing-doc lint lib + extend coverage

Move LINT_PATTERN/CARVEOUT_PATTERN/lint_about_content/run_lint from
scripts/build_about_content.py into multiomics_explorer/_outfacing_lint.py
(rename lint_about_content -> lint_lines with back-compat alias). Add
lint_python_docstrings AST scanner. Extend CLI --lint to sweep
api/functions.py, multiomics_explorer/analysis/*.py, hand-authored md
(guide + analysis), and examples (.py + README.md).

Adds 5 parametrized lint gates in layer-colocated test files. Gates
fail today on the surfaces inventoried in the round-2 spec; cleanup
follows in subsequent commits.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify commit**

Run: `git log -1 --stat`
Expected: 1 new module, 1 modified script, 5 modified/new test files, 1 renamed test file.

---

## Task 10: Update layer-rules surface map (step 2.1)

**Files:**
- Modify: `.claude/skills/layer-rules/references/layer-boundaries.md` (table at lines 416-427)

**Process note:** Use the `skill-creator` skill if invoking via Skill tool; otherwise hand-edit per skill conventions (existing voice + structure). The change is a table-row insert + softener removal + paragraph add — no new skill conventions invented.

- [ ] **Step 1: Read the current table**

Run: `sed -n '410,430p' .claude/skills/layer-rules/references/layer-boundaries.md`
Expected: 10 rows from `kg/queries_lib.py` to `CLAUDE.md`.

- [ ] **Step 2: Apply 5 edits to the table**

Edit `.claude/skills/layer-rules/references/layer-boundaries.md`:

1. **Add row for `multiomics_explorer/analysis/*.py` docstrings** immediately after the `api/functions.py` row (line ~419):

   ```
   | `multiomics_explorer/analysis/*.py` docstrings | **Yes** — Python API users (`help(response_matrix)`) and LLM agents via the rendered analysis md | Yes (Python-API audience accent — same as `api/functions.py`) |
   ```

2. **Drop softener on guide row** (line ~425):

   Change:
   ```
   | `skills/.../references/guide/*.md` | **Yes** — hand-authored | Yes (rare edits) |
   ```
   To:
   ```
   | `skills/.../references/guide/*.md` | **Yes** — hand-authored | Yes |
   ```

3. **Drop softener on analysis row** (line ~426):

   Change:
   ```
   | `skills/.../references/analysis/*.md` | **Yes** — hand-authored | Yes (best-effort) |
   ```
   To:
   ```
   | `skills/.../references/analysis/*.md` | **Yes** — hand-authored | Yes |
   ```

4. **Add row for `examples/*.py`** immediately before the `CLAUDE.md` row (line ~427):

   ```
   | `examples/*.py` | **Yes** — served at `docs://examples/{file}`; agents read whole file | Yes (whole-file scan: comments ARE outfacing here) |
   ```

5. **Add row for `examples/README.md`** immediately after the new `examples/*.py` row:

   ```
   | `examples/README.md` | **Yes** — served at `docs://examples/{file}` | Yes |
   ```

- [ ] **Step 3: Add the Scanner notes paragraph**

After the table (just before the `---` on line ~429), insert:

```markdown
**Scanner notes (lint mode per surface):**

- Tool docstring + Pydantic `Field(description=...)`: caught indirectly via the rendered tool-md scan.
- `api/functions.py` and `multiomics_explorer/analysis/*.py` docstrings: AST-extracted; `# ...` comments are not scanned (per the surface-map rows above).
- `examples/*.py`: whole file scanned line-by-line — comments ARE outfacing here, since the file IS the artifact.
- Hand-authored md (`analysis/`, `guide/`, `examples/README.md`): line-by-line.

```

- [ ] **Step 4: Verify table now has 13 rows**

Run: `awk '/^## Outfacing-doc surface map/,/^---$/' .claude/skills/layer-rules/references/layer-boundaries.md | grep -c '^|'`
Expected: 15 (1 header + 1 separator + 13 data rows).

- [ ] **Step 5: Verify softeners are gone**

Run: `grep -n 'rare edits\|best-effort' .claude/skills/layer-rules/references/layer-boundaries.md`
Expected: No output (both softeners removed).

- [ ] **Step 6: Run unit tests to confirm no regression**

Run: `pytest tests/unit/ -q 2>&1 | tail -5`
Expected: Same failure count as Task 9 — no new failures introduced.

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/layer-rules/references/layer-boundaries.md
git commit -m "$(cat <<'EOF'
docs(skill): close gaps in outfacing-doc surface map

Add rows for examples/*.py, examples/README.md, and analysis/*.py
docstrings (3 outfacing surfaces missed by round 1). Drop the
"(rare edits)" and "(best-effort)" softeners from guide and analysis
md rows - both surfaces had violations slip through round 1 and
follow the same rules at the same weight as the MCP surfaces.
Add Scanner notes paragraph clarifying lint mode per surface.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Update add-or-update-tool skill briefs (step 2.2)

**Files:**
- Modify: `.claude/skills/add-or-update-tool/SKILL.md`

**Process note:** Use the `skill-creator` skill if invoking via Skill tool; otherwise hand-edit per skill conventions. Three terse cross-references to the 9 rules — no verbatim duplication of the rules themselves.

- [ ] **Step 1: Read the relevant sections**

Run: `grep -n 'api-updater\|doc-updater\|Stage 3 step 1\|mechanical backstop' .claude/skills/add-or-update-tool/SKILL.md`
Expected: Lines for the three edit targets — note them.

- [ ] **Step 2: Add api-updater outfacing-surface brief**

Locate the `api-updater` agent's brief paragraph (around line 109 area). Append the following to that paragraph (or add as an indented bullet/sub-paragraph if the existing structure uses bullets):

> Function docstrings on `api/functions.py` AND `multiomics_explorer/analysis/*.py` are agent-outfacing — they reach Python users via `help()` and LLM agents via the rendered tool md's "Package import equivalent" path and via `docs://analysis/{name}`. The 9 outfacing-doc style rules from the round-1 readability-pass spec apply with a Python-API audience accent: dict keys, raised exceptions, return shape — not agent-routing language. Run `uv run python scripts/build_about_content.py --lint` after editing.

- [ ] **Step 3: Add doc-updater outfacing-surface brief**

Locate the `doc-updater` agent's brief paragraph. Append:

> Analysis md (`references/analysis/*.md`) and example .py files (`examples/*.py`) are agent-outfacing — they're served at `docs://analysis/{name}` and `docs://examples/{file}`. The 9 outfacing-doc style rules apply. Audience accent: analysis = cross-tool methodology with biological precision; examples = task-oriented runnable code where comments explain the pattern, not biology lore. Run `uv run python scripts/build_about_content.py --lint` after editing.

- [ ] **Step 4: Update Stage 3 step 1 cross-reference**

Locate the existing line that says "Mechanical backstop for the outfacing-doc style rules" (Stage 3 step 1 area). Append to that paragraph:

> Now covers MCP md, api docstrings, analysis docstrings, hand-authored md (analysis + guide), and `examples/*.py`.

- [ ] **Step 5: Verify no verbatim restatement of the 9 rules**

Run: `grep -n 'ISO date\|today count\|Phase N' .claude/skills/add-or-update-tool/SKILL.md`
Expected: No new matches (or only matches that already existed) — rules live in the round-1 spec, not in this skill.

- [ ] **Step 6: Run unit tests**

Run: `pytest tests/unit/ -q 2>&1 | tail -5`
Expected: Same failure count as before — no new failures.

- [ ] **Step 7: Commit**

```bash
git add .claude/skills/add-or-update-tool/SKILL.md
git commit -m "$(cat <<'EOF'
docs(skill): brief api-updater and doc-updater on outfacing surfaces

api-updater now owns api/functions.py AND analysis/*.py docstrings;
doc-updater now owns analysis md + examples/*.py. Both briefs
cross-link to the round-1 readability-pass spec rather than restating
the 9 rules. Stage 3 step 1 reflects expanded --lint coverage.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: D4 — clean guide md (smallest sweep first)

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/guide/python_api.md` (3 violations)
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/guide/conventions.md` (2 violations)

**Audience accent:** cross-cutting preamble — terse, high-level. Drop time-stamped counts and internal-history shorthand; keep cross-cutting concepts.

- [ ] **Step 1: List violations**

Run: `uv run python scripts/build_about_content.py --lint multiomics_explorer/skills/multiomics-kg-guide/references/guide/python_api.md multiomics_explorer/skills/multiomics-kg-guide/references/guide/conventions.md 2>&1`
Expected: ~5 violations across the 2 files; each line printed as `path:line: 'token' in: <text>`.

- [ ] **Step 2: Edit each violation**

For each reported line, open the file at the indicated line and rewrite the line to remove the shorthand while preserving the substance. Cross-reference the round-1 spec at `docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md` for the 9 rules and example rewrites if unsure.

Common fixes:
- `parent §13.6` → name the section directly, e.g. `the not_found rubric`.
- `Phase 2` → drop the phase tag; describe the change directly.
- `2026-05-04 release` → drop the date; describe the change directly.
- `audit §4.3.3` → drop the audit reference; state the fact.

- [ ] **Step 3: Verify gate green**

Run: `pytest tests/unit/test_guide_about_content.py -q`
Expected: All 4 IDs pass.

- [ ] **Step 4: Run full unit suite to confirm no regression**

Run: `pytest tests/unit/ -q 2>&1 | tail -5`
Expected: Step 1's failures still present minus the 2 guide-md IDs that just went green.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/guide/
git commit -m "$(cat <<'EOF'
docs(guide): drop residual shorthand from guide files

Round-2 sweep on hand-authored guide md - 5 violations across
python_api.md and conventions.md. Audience accent: cross-cutting
preamble; terse, high-level. No content removed beyond
internal-history shorthand and time-stamped counts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: D3 — clean examples

**Files:**
- Modify: `examples/metabolites.py` (11 violations)
- Possibly modify: `examples/README.md`, `examples/pathway_enrichment.py` (verify clean)

**Audience accent:** task-oriented runnable code. Comments explain the *pattern* the example demonstrates, not biology lore. Drop Phase N, KG release dates, audit refs from comments.

- [ ] **Step 1: List violations**

Run: `uv run python scripts/build_about_content.py --lint examples/metabolites.py examples/pathway_enrichment.py examples/README.md 2>&1`
Expected: ~11 violations in `metabolites.py`; possibly clean for the other two.

- [ ] **Step 2: Edit comments in `examples/metabolites.py`**

For each reported line, rewrite the comment to focus on the pattern being demonstrated. Common fixes:
- `# Phase 2 cleanup of the metabolites tool` → drop or rewrite as `# the metabolites tool`.
- `# 2026-05-05 KG release added X` → drop the date; describe the feature directly.
- `# audit §4.3.3 says Y` → state Y directly.

Preserve runnable code semantics — only edit comments and any docstrings.

- [ ] **Step 3: Scan README and other example files**

If the README or `pathway_enrichment.py` reported violations, apply the same audience-accent rewrites.

- [ ] **Step 4: Verify gate green**

Run: `pytest tests/unit/test_examples_about_content.py -q`
Expected: All IDs pass.

- [ ] **Step 5: Verify examples still runnable** (smoke test — only if Neo4j is available; skip otherwise)

Run: `uv run python examples/metabolites.py 2>&1 | head -10`
Expected: Either successful output or a Neo4j-connection error — not a syntax error or import error.

- [ ] **Step 6: Run full unit suite**

Run: `pytest tests/unit/ -q 2>&1 | tail -5`
Expected: Step 1's failures minus 2 guide-md (Task 12) minus the examples IDs that just went green.

- [ ] **Step 7: Commit**

```bash
git add examples/
git commit -m "$(cat <<'EOF'
docs(examples): readability pass on examples

Round-2 sweep on examples/ (whole-file outfacing surface). Audience
accent: task-oriented runnable code; comments explain the pattern, not
biology lore. Drop Phase N tags, KG release dates, and audit references
from comments. No code semantics change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: D2 — clean analysis md

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` (26 violations)
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md` (9 violations)
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/derived_metrics.md` (3 violations)

**Audience accent:** cross-tool analysis methodology with biological precision. Drop internal-history shorthand and time-stamped counts. **Keep** biological caveats and "permanent KG limitation" notes — those are substance.

- [ ] **Step 1: List violations**

Run: `uv run python scripts/build_about_content.py --lint multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md multiomics_explorer/skills/multiomics-kg-guide/references/analysis/derived_metrics.md 2>&1`
Expected: ~38 violations across the 3 files (26 + 9 + 3).

- [ ] **Step 2: Edit `metabolites.md` (the densest)**

Common patterns to fix in `metabolites.md`:
- `Part 4 §4.1.1` / `audit §4.1.2` / `§b2` / `§g` → name the section directly or drop the cross-ref entirely.
- `Phase 2` / `Phase 3` → drop the phase tag.
- `KG-A5` / `KG-MET-011` → drop the ticket ID; describe the limitation directly.
- `KG release 2026-05-05 added X` → drop the date; state X.
- `today (149 metabolites)` → drop "today"; either state the count without the temporal hedge or omit the count.

Preserve:
- Named compounds and pathway names (biological precision).
- "Permanent KG limitation" notes — these are durable substance.
- Cross-tool methodology guidance.

- [ ] **Step 3: Edit `enrichment.md`**

Same approach — 9 violations.

- [ ] **Step 4: Edit `derived_metrics.md`**

Same approach — 3 violations.

- [ ] **Step 5: Verify gate green**

Run: `pytest tests/unit/test_analysis_about_content.py::test_analysis_md_lint_clean -q`
Expected: All 3 IDs pass.

- [ ] **Step 6: Run full unit suite**

Run: `pytest tests/unit/ -q 2>&1 | tail -5`
Expected: Step 1's failures minus what's now green from Tasks 12-13 minus the 3 analysis md IDs that just went green.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/
git commit -m "$(cat <<'EOF'
docs(analysis): readability pass on analysis md

Round-2 sweep on hand-authored analysis md - 38 violations across 3
files (26 + 9 + 3). Audience accent: cross-tool analysis methodology
with biological precision. Drop internal-history shorthand
(parent §, KG-XXX-NNN, Phase N, audit refs, time-stamped release
dates); keep biological caveats and permanent KG limitation notes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: D5 — clean analysis function docstrings

**Files:**
- Modify: docstrings in `multiomics_explorer/analysis/expression.py`, `frames.py`, `enrichment.py` (count TBD — discovered in Task 9)

**Audience accent:** Python users + LLM agents on package-import. Same accent as Task 16 (api). Lead with what the function returns; note raised exceptions; avoid agent-routing phrases ("drill into Y", "chain via Z").

- [ ] **Step 1: List violations**

Run: `uv run python scripts/build_about_content.py --lint multiomics_explorer/analysis/expression.py multiomics_explorer/analysis/frames.py multiomics_explorer/analysis/enrichment.py 2>&1`
Expected: A list of violations (count varies).

- [ ] **Step 2: Edit each docstring**

For each reported line, locate the function and rewrite the docstring line. Common patterns:
- `parent §13.6` → name the rubric directly.
- `Phase 2` → drop the phase tag.
- `2026-05-04 release added Y` → drop the date; state Y.
- `audit §X.Y` → drop the audit reference.

Lead each docstring with one line stating what the function returns (dict keys, DataFrame columns, etc.). Note raised exceptions where relevant.

**Do not** change function signatures or behavior — docstring content only.

- [ ] **Step 3: Verify gate green**

Run: `pytest tests/unit/test_analysis_about_content.py::test_analysis_function_docstring_lint_clean -q`
Expected: All IDs pass.

- [ ] **Step 4: Verify other analysis tests still pass**

Run: `pytest tests/unit/test_analysis.py tests/unit/test_enrichment.py tests/unit/test_enrichment_result.py tests/unit/test_frames.py -q`
Expected: All pass — no behavior changed.

- [ ] **Step 5: Run full unit suite**

Run: `pytest tests/unit/ -q 2>&1 | tail -5`
Expected: Only `test_api_function_docstring_lint_clean[*]` failures remain.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/analysis/
git commit -m "$(cat <<'EOF'
docs(analysis-py): readability pass on analysis function docstrings

Round-2 sweep on multiomics_explorer/analysis/*.py docstrings.
Audience accent: Python API users (help(response_matrix)) and LLM
agents via the rendered analysis md. Drop internal-history shorthand;
lead each docstring with what the function returns; note raised
exceptions. No function semantics changed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: D1 — clean api/functions.py docstrings (the big one)

**Files:**
- Modify: `multiomics_explorer/api/functions.py` (~50 functions, ~100-300 violations)

**Audience accent:** Python users + LLM agents on package-import. Lead with what the function returns (one-line dict-keys summary). Note `raises ValueError` / `raises Neo4jClientError` where relevant. Cross-link to MCP tool name only when the api function 1:1 mirrors a tool. Avoid agent-routing phrases ("drill into Y", "chain via Z") — those belong on the MCP surface.

**Strategy:** sweep alphabetically by function name, running the gate periodically to track progress. Each pass narrows the failing-IDs list visible in pytest output.

- [ ] **Step 1: List per-function failures**

Run: `pytest tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean -q 2>&1 | grep FAIL | head -20`
Expected: Many lines like `FAILED tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean[gene_overview]`.

- [ ] **Step 2: Run lint on the file to see all violations at once**

Run: `uv run python scripts/build_about_content.py --lint multiomics_explorer/api/functions.py 2>&1 | head -50`
Expected: Many violations with `file:line: 'token'` format.

- [ ] **Step 3: Sweep in batches** (recommended: 10 functions per batch)

For each batch:

a. Pick the next ~10 failing functions by name. View their docstrings:
   ```bash
   pytest tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean -q 2>&1 | grep FAIL | head -10
   ```

b. For each function, edit its docstring per the audience-accent guidance. Common patterns:
   - **Lead line:** "Return per-gene rows with detection_status, value, timepoint." (state output up front)
   - Drop `parent §13.6` → name the rubric: `the not_found rubric`.
   - Drop `Phase 2` → describe the change directly.
   - Drop `2026-05-05 KG release` → drop the date.
   - Drop `audit §X.Y` → drop the reference.
   - Drop `chain via Y` → that belongs on the MCP tool; on api the call is `multiomics_explorer.Y(...)`.
   - Drop `drill into Y` → describe the relationship directly.
   - **Add `raises:`** where the function raises (`raises ValueError`, `raises Neo4jClientError`).

c. Re-run the per-function gate for the batch:
   ```bash
   pytest 'tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean[fn1]' \
          'tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean[fn2]' \
          ... -q
   ```
   Expected: All in the batch pass.

d. Make an intermediate commit per batch (optional but recommended for review):

   ```bash
   git add multiomics_explorer/api/functions.py
   git commit -m "docs(api): readability pass on N-Z functions (batch K)" --no-verify
   ```

   Or save all batches to one commit at the end (Step 5).

- [ ] **Step 4: Final verify — full gate green**

Run: `pytest tests/unit/test_api_functions.py::test_api_function_docstring_lint_clean -q 2>&1 | tail -5`
Expected: All ~50 IDs pass.

- [ ] **Step 5: Verify api behavior unchanged**

Run: `pytest tests/unit/test_api_functions.py -q`
Expected: All pass — no behavior changed.

Spot-check via `help()`:
```bash
uv run python -c "import multiomics_explorer; help(multiomics_explorer.gene_overview)" | head -40
```
Expected: Reads cleanly to a Python user — leads with returns, notes exceptions, no archaeology dumps.

- [ ] **Step 6: Final commit (or rebase batches into one)**

If you used per-batch commits, optionally squash:
```bash
git rebase -i HEAD~K  # K = number of batch commits
```

If you saved everything to step 5 directly, commit now:

```bash
git add multiomics_explorer/api/functions.py
git commit -m "$(cat <<'EOF'
docs(api): readability pass on api/functions.py docstrings

Round-2 sweep on api/functions.py docstrings (~50 functions).
Audience accent: Python users + LLM agents on package-import. Each
docstring leads with what the function returns; raised exceptions
documented; agent-routing phrases moved to MCP surface only. Drop
internal-history shorthand. No function semantics changed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Final verification and merge

- [ ] **Step 1: Lint exits clean**

Run: `uv run python scripts/build_about_content.py --lint`
Expected: `Lint clean.` and exit code 0.

- [ ] **Step 2: All unit tests green**

Run: `pytest tests/unit/ -q 2>&1 | tail -5`
Expected: All passed.

- [ ] **Step 3: Spot-read 5 surfaces**

a. A guide page:
   ```bash
   head -60 multiomics_explorer/skills/multiomics-kg-guide/references/guide/python_api.md
   ```
   Expected: Reads as cross-cutting preamble; no shorthand; no archaeology.

b. An analysis md page:
   ```bash
   head -80 multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
   ```
   Expected: Reads as cross-tool methodology; biological precision intact; no `parent §`, no `Phase N`, no `KG-XXX-NNN`.

c. An analysis function docstring:
   ```bash
   uv run python -c "import multiomics_explorer; help(multiomics_explorer.response_matrix)" | head -30
   ```
   Expected: Leads with what's returned; no internal-history shorthand.

d. An example .py:
   ```bash
   head -50 examples/metabolites.py
   ```
   Expected: Comments explain the pattern, not biology lore; no Phase N or release-date references.

e. An api function docstring:
   ```bash
   uv run python -c "import multiomics_explorer; help(multiomics_explorer.gene_overview)" | head -50
   ```
   Expected: Leads with returns; raises documented; no agent-routing phrases.

- [ ] **Step 4: Review the commit log on the branch**

Run: `git log main..HEAD --oneline`
Expected: 8 commits — 1 step-1 (lib + tests, Task 9), 2 step-2 (surface map + skill briefs, Tasks 10-11), 5 step-3 cleanups (D4 → D3 → D2 → D5 → D1, Tasks 12-16). If you used per-batch commits in Task 16 and didn't squash, the count is higher.

- [ ] **Step 5: Merge worktree to main**

From outside the worktree (e.g., main repo at `/home/osnat/github/multiomics_explorer`):

```bash
cd /home/osnat/github/multiomics_explorer
git checkout main
git merge --ff-only outfacing-docs-round-2
```

Expected: Fast-forward merge succeeds. If non-FF (because main moved), rebase the branch on main first:

```bash
cd .claude/worktrees/outfacing-docs-round-2
git fetch origin
git rebase main
# resolve conflicts if any
cd /home/osnat/github/multiomics_explorer
git merge --ff-only outfacing-docs-round-2
```

- [ ] **Step 6: Clean up the worktree**

```bash
git worktree remove .claude/worktrees/outfacing-docs-round-2
git branch -d outfacing-docs-round-2
```

- [ ] **Step 7: Final post-merge sanity**

```bash
pytest tests/unit/ -q
uv run python scripts/build_about_content.py --lint
```
Expected: Both clean on main.

---

## Cross-cutting reminders

**Single commit per logical unit.** Step 1 is one big commit (lib + tests are coupled). Step 2 is two commits. Step 3 is five commits.

**No verbatim duplication of the 9 rules** in skill files — they live in `layer-rules` + the round-1 readability-pass spec. Skill briefs cross-link.

**Carveout `[AQ]`/`[ENR]` is uniform.** A docstring genuinely needing a drift-marker tag is allowed; spot-review whether the tag is appropriate.

**No behavior changes anywhere.** If a docstring surfaces that the *function* is wrong, fix the doc, do not silently retune what the function does.

**Worktree branched from local main.** Local main is ahead of origin/main by 6 commits — those local commits are part of the slice's premise. Do not branch from origin/main.
