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
