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


def test_lint_catches_capitalized_audit(lint_mod, tmp_path):
    """'Audit Part 3a P0' in examples/metabolites.py slipped the lowercase-only pattern."""
    md = tmp_path / "t.md"
    md.write_text("Build-derived note (Audit Part 3a P0).\n")
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


def test_lint_catches_retired_catalysis_arm_names(lint_mod, tmp_path):
    """Retired 2026-08 KG names: dotted property forms + routing example."""
    md = tmp_path / "t.md"
    md.write_text(
        "Reads Gene.metabolite_count for the rollup.\n"
        "OrganismTaxon.metabolite_count ranks organisms.\n"
        "Metabolite.gene_count routes to genes_by_metabolite.\n"
        "Chain via results[].gene_count > 0.\n"
    )
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 4


def test_lint_catches_retired_tcdb_trust_vocabulary(lint_mod, tmp_path):
    """Retired 2026-08 TCDB terms: precision-tier label, family-inferred dominance."""
    md = tmp_path / "t.md"
    md.write_text(
        "See section g (precision-tier) for the split.\n"
        "Warn on family_inferred dominance of transport rows.\n"
    )
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 2


def test_lint_catches_retired_name_lineage(lint_mod, tmp_path):
    """'successor of the removed X' is CHANGELOG lineage, not usage guidance
    (gene_overview tcdb_family_count description)."""
    md = tmp_path / "t.md"
    md.write_text(
        "The corrected successor of the removed transporter_count.\n"
        "A replacement for the retired metabolite_count column.\n"
        "The successor family sits one level below its parent.\n"
    )
    vs = lint_mod.lint_about_content([md])
    assert [v[1] for v in vs] == [1, 2]


def test_lint_ignores_legitimate_count_names(lint_mod, tmp_path):
    """Bare gene_count / measured metabolite_count remain valid elsewhere."""
    md = tmp_path / "t.md"
    md.write_text(
        "Ontology-node gene_count means genes annotated to the term.\n"
        "Per-row metabolite_count counts measured metabolites.\n"
        "catalyzed_metabolite_count and catalyst_gene_count are the arms.\n"
    )
    vs = lint_mod.lint_about_content([md])
    assert vs == []


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


# ---------------------------------------------------------------------------
# Dangling internal cross-reference: `see "Section" above|below`
# ---------------------------------------------------------------------------


def test_dangling_ref_flags_a_missing_section(lint_mod, tmp_path):
    """The source violation: a pointer at a section that was never written."""
    md = tmp_path / "t.md"
    md.write_text(
        "# Annotation trust\n"
        "\n"
        "picking the one edge whose trust columns populate an ancestor row (see\n"
        '"One edge per (gene, term)" below). Ontologies without a rank_prop are\n'
        "either flat or carry no score at all.\n"
    )
    vs = lint_mod.lint_about_content([md])
    assert len(vs) == 1
    # The phrase wraps, so the match is anchored at the line carrying `see`.
    assert vs[0][1] == 3
    assert "One edge per (gene, term)" in vs[0][3]


def test_dangling_ref_resolves_against_a_heading_in_the_same_file(
    lint_mod, tmp_path,
):
    md = tmp_path / "t.md"
    md.write_text(
        "# Annotation trust\n"
        "\n"
        'The ancestor row takes the best edge (see "One edge per (gene, term)"\n'
        "below).\n"
        "\n"
        "## One edge per (gene, term)\n"
        "\n"
        "Highest rank_prop wins.\n"
    )
    assert lint_mod.lint_about_content([md]) == []


def test_dangling_ref_tolerates_numbering_and_qualifiers(lint_mod, tmp_path):
    """`## 12. Gotchas` answers a pointer that just says "Gotchas"."""
    md = tmp_path / "t.md"
    md.write_text(
        "# Enrichment\n"
        "\n"
        'Term size is the background-scoped size. See "Gotchas" below.\n'
        "\n"
        "## 12. Gotchas\n"
    )
    assert lint_mod.lint_about_content([md]) == []


def test_dangling_ref_ignores_docs_cross_links(lint_mod, tmp_path):
    """A `docs://` cross-link is the sanctioned form and carries no quotes."""
    md = tmp_path / "t.md"
    md.write_text(
        "# Annotation trust\n"
        "\n"
        "See docs://analysis/annotation_evidence below for the full ladder.\n"
    )
    assert lint_mod.lint_about_content([md]) == []


def test_dangling_ref_ignores_quoted_values(lint_mod, tmp_path):
    """A quoted *value* is not a section pointer, even next to above/below."""
    md = tmp_path / "t.md"
    md.write_text(
        "# Annotation trust\n"
        "\n"
        'Rows default to "most_specific" above; see "most_specific" below.\n'
        'Tier sits at or above 2; the table above lists "curated" first.\n'
    )
    assert lint_mod.lint_about_content([md]) == []


def test_lint_catches_field_descriptions(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text(
        "Docs and Field descriptions may list stale values.\n"
        "One Field description per parameter.\n"
        "Parameter descriptions may list stale values.\n"
    )
    vs = lint_mod.lint_about_content([md])
    assert [v[1] for v in vs] == [1, 2]
    assert vs[0][3] == "Field descriptions"
    assert vs[1][3] == "Field description"


def test_lint_catches_release_note_previously(lint_mod, tmp_path):
    """'previously 0 rows' in a served mistakes entry: the reader has no 'previously'."""
    md = tmp_path / "t.md"
    md.write_text("bare KEGG id — previously 0 rows, `C00064` in not_found\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) >= 1


def test_lint_catches_release_note_are_now_resolved(lint_mod, tmp_path):
    md = tmp_path / "t.md"
    md.write_text("Bare metabolite IDs are now resolved via cross-references.\n")
    vs = lint_mod.lint_about_content([md])
    assert len(vs) >= 1


def test_lint_ignores_present_tense_type_note(lint_mod, tmp_path):
    """'`ontology` is now `str | list[str]`' is a type description, not release framing."""
    md = tmp_path / "t.md"
    md.write_text("`ontology` is now `str | list[str] | None`.\n")
    vs = lint_mod.lint_about_content([md])
    assert vs == []


def test_lint_skips_example_response_fences(lint_mod, tmp_path):
    """Live payloads inside ```example-response fences are data, not prose."""
    md = tmp_path / "t.md"
    md.write_text(
        "Prose line.\n```example-response\n"
        '{"description": "previously described"}\n```\n'
        "Released on 2026-05-06.\n"
    )
    vs = lint_mod.lint_about_content([md])
    assert [v[1] for v in vs] == [5]
