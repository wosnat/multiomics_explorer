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
    r"|\b[Aa]udit\b"         # internal audit ref (either case; "Audit Part 3a" slipped through)
    r"|KG-[A-Z]+-[0-9]"       # KG-XXX-NNN ticket ID
    r"|Mode-[A-Z]\b"          # Mode-A / Mode-B template tag
    r"|Cluster [A-Z]\b"       # Cluster A / Cluster B internal tag
    r"|parent §"              # cross-ref shorthand
    # Release-note framing in served docs: the reader has no "previously".
    # Source violation: inputs/tools/list_metabolites.yaml mistakes entry
    # ("previously 0 rows", "are now resolved via").
    r"|\bpreviously\b"
    r"|\b(?:is|are) now (?:resolved|accepted|coerced|supported)\b"
    # Retired catalysis-arm names (2026-08 KG rename). Context-anchored on
    # purpose: bare gene_count / metabolite_count stay legitimate elsewhere
    # (ontology-node gene_count, Experiment/Publication measured counts).
    # Source violations: guide/conventions.md results[].gene_count routing
    # example; dotted retired-property forms in guide/concepts.md.
    r"|\b(?:Gene|OrganismTaxon)\.metabolite_count\b"
    r"|\bMetabolite\.gene_count\b"
    r"|results\[\]\.gene_count"
    # Retired TCDB trust vocabulary (2026-08 substrate_depth migration).
    # Source violations: analysis/metabolites.md decision-tree label
    # "g (precision-tier)"; the pre-migration warning concept.
    r"|precision[ -]tier"
    r"|family[ _-]inferred[ _-]dominance"
    # Pydantic-internal vocabulary leaking into agent-facing text: agents see
    # parameter descriptions, not "Field descriptions" (kg_release_info
    # vocabulary-mismatch sentence).
    r"|\bField descriptions?\b"
    # Retired-name lineage ("the corrected successor of the removed
    # transporter_count"): what a column replaced is CHANGELOG material,
    # not usage guidance. Source violation: the gene_overview
    # tcdb_family_count parameter description and example comment.
    r"|\b(?:successor|replacement)s? (?:of|for|to) the (?:removed|retired|old)\b"
)

# Drift-marker carveout. The [AQ] (annotation_quality redefinition) and
# [ENR] (informative_only=True default flip) markers stay as 1-line inline
# notes on affected tools.
CARVEOUT_PATTERN = re.compile(r"\[AQ\]|\[ENR\]")

# Dangling internal cross-reference: `see "Some Section" above|below` whose
# quoted text names no heading in the same file. Deliberately narrow —
# a `see docs://...` cross-link carries no quotes, and a quoted *value*
# ("most_specific") is lowercase and is not followed by above/below. The
# `\s+` spans newlines because the phrase often wraps.
# Source violation: analysis/annotation_evidence.md's pointer at the
# per-ontology trust table, which named a section that did not exist.
DANGLING_REF_PATTERN = re.compile(
    r"[Ss]ee\s+[\"“]`?([A-Z][^\"”\n]{2,80})[\"”]\s+(?:above|below)\b"
)

_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)

Violation = tuple[Path, int, str, str]


def _normalize_ref(text: str) -> str:
    """Heading / reference text reduced to a comparable form."""
    return re.sub(r"[`*_]", "", text).strip().strip(".").lower()


def _dangling_refs(path: Path, text: str) -> list[Violation]:
    """`see "X" above|below` matches with no `X` heading in the same file.

    A reference resolves when its text appears anywhere inside a heading,
    so section numbering (`## 12. Gotchas`) and trailing qualifiers
    (`## Partial-failure buckets: ...`) do not have to be quoted back.
    """
    headings = [_normalize_ref(m.group(1)) for m in _HEADING_RE.finditer(text)]
    lines = text.splitlines()
    out: list[Violation] = []
    for m in DANGLING_REF_PATTERN.finditer(text):
        ref = _normalize_ref(m.group(1))
        if any(ref in heading for heading in headings):
            continue
        line_no = text.count("\n", 0, m.start()) + 1
        line = lines[line_no - 1] if line_no <= len(lines) else ""
        if CARVEOUT_PATTERN.search(line):
            continue
        out.append((path, line_no, line, m.group(0)))
    return out


def lint_lines(paths: list[Path]) -> list[Violation]:
    """Line-by-line scan. Used for md, examples/*.py (whole file), README.

    Returns ``(path, line_no, line, matched_token)`` per violation.
    Lines containing ``[AQ]`` / ``[ENR]`` drift markers are exempt.

    One rule needs the whole file rather than one line: a
    ``see "Section" above|below`` pointer is only a violation when no
    heading in that same file answers to it.
    """
    violations: list[Violation] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"  SKIP {path}: {e}", file=sys.stderr)
            continue
        in_example_block = False
        for i, line in enumerate(text.splitlines(), 1):
            # ```example-response fences hold live KG payloads (term
            # descriptions, product names) — data, not prose; skip them.
            stripped = line.strip()
            if stripped.startswith("```"):
                in_example_block = (
                    not in_example_block and stripped.startswith("```example-response")
                )
                continue
            if in_example_block:
                continue
            if CARVEOUT_PATTERN.search(line):
                continue
            m = LINT_PATTERN.search(line)
            if m:
                violations.append((path, i, line, m.group(0)))
        violations.extend(_dangling_refs(path, text))
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
            text = path.read_text(encoding="utf-8")
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
