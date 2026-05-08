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
