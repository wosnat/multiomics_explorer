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


def test_conventions_within_budget_and_pointers_present():
    text = (GUIDE_DIR / "conventions.md").read_text()
    assert len(text) <= 28000, f"conventions.md {len(text)} chars > 28k (~7k tok)"
    for moved, home in [
        ("Transport trust ladder", "docs://analysis/metabolites"),
        ("Metabolite ID forms", "docs://analysis/metabolites"),
        ("Annotation-trust surface", "docs://analysis/annotation_evidence"),
    ]:
        assert home in text, f"pointer to {home} missing"
        assert f"## {moved}" not in text, f"section '{moved}' should have moved to {home}"


def test_start_here_budget_and_recipes():
    text = (GUIDE_DIR / "start_here.md").read_text()
    assert len(text) <= 16000, f"start_here.md {len(text)} chars > 16k (~4k tok)"
    assert "cross-feeding" in text.lower()
    assert "ontology_landscape" in text
