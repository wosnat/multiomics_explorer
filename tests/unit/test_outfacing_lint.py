"""Tests for the outfacing-doc lint scanners in multiomics_explorer._outfacing_lint.

The lint regex catches the 9 outfacing-doc style rules from
docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
that are mechanically detectable.

[AQ] and [ENR] drift markers are exempt — see rule 3 carveout.

Two scanners covered:
- ``lint_lines`` (and its back-compat alias ``lint_about_content``) — line-by-line.
- ``lint_python_docstrings`` — AST-walk on .py files; only docstrings are scanned.
"""

import io
from pathlib import Path

import pytest

from multiomics_explorer import _outfacing_lint as lint_mod_real


@pytest.fixture(scope="module")
def lint_mod():
    return lint_mod_real


def test_lint_function_exists(lint_mod):
    assert hasattr(lint_mod, "lint_about_content")
    assert hasattr(lint_mod, "run_lint")


def test_lint_catches_iso_date(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("Released on 2026-05-06.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1
    assert vs[0][1] == 1


def test_lint_catches_today_count(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("149 metabolites today have evidence.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1


def test_lint_catches_section_marker(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("See §10 for tested-absent semantics.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1


def test_lint_catches_phase_tag(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("Renamed from `search` in Phase 2.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1


def test_lint_catches_audit_word(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("audit §4.3.3 primary headline.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) >= 1


def test_lint_catches_kg_ticket(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("Pending KG-MET-002 backfill.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1


def test_lint_catches_mode_tag(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("Built using the Mode-B template.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1


def test_lint_catches_cluster_tag(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("Cluster A surface landed last week.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1


def test_lint_ignores_biological_d_tags(lint_mod, tmp_path):
    """D1, D3 etc. collide with photosystem proteins / timepoint labels."""
    md = tmp_path / "t.md"
    md.write_text(
        "Photosystem II D1 protein.\n"
        "D3 sentinel-stripped timepoints.\n"
        "F-class proteins recovered.\n"
    )
    vs = lint_mod.lint_about_content([md])
    assert vs == []


def test_lint_catches_parent_section(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("See parent §13.6 for not_found shape.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) >= 1


def test_lint_carveout_aq_marker(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("[AQ] redefined 2026-05-01: annotation_state encoding.\n")
    vs = lint_mod.lint_about_content([md])
    assert vs == []


def test_lint_carveout_enr_marker(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("[ENR] informative_only=True default flip 2026-05-04.\n")
    vs = lint_mod.lint_about_content([md])
    assert vs == []


def test_lint_clean_line_passes(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("Returns gene-level summary across treatments.\n")
    vs = lint_mod.lint_about_content([md])
    assert vs == []


def test_lint_reports_file_line_and_token(lint_mod, tmp_path):
    md = tmp_path / "tool.md"
    md.write_text("ok\nbad: see parent §10\nok again\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1
    path, line_no, line, token = vs[0]
    assert path == md
    assert line_no == 2
    assert "parent §" in token or "§" in token


def test_run_lint_exit_zero_on_clean_input(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("Plain prose with no violations.\n")
    buf = io.StringIO()
    rc = lint_mod.run_lint([md], stream=buf)
    assert rc == 0


def test_run_lint_exit_nonzero_on_violation(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("This has 149 today.\n")
    buf = io.StringIO()
    rc = lint_mod.run_lint([md], stream=buf)
    assert rc != 0
    out = buf.getvalue()
    assert "t.md" in out
    assert "1:" in out


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
    # KG-XYZ-001 matches as 'KG-XYZ-0' (regex captures one trailing digit).
    assert tokens == ["KG-XYZ-0", "Phase 2", "§"]


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
