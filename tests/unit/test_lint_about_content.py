"""Tests for the readability-pass lint mode in build_about_content.py.

The lint regex catches the 9 outfacing-doc style rules from
docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
that are mechanically detectable (rules 1, 2, 3, 4 — the 197+ violation
patterns documented in the readability-pass commit history).

[AQ] and [ENR] drift markers are exempt — see rule 3 carveout.
"""

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


