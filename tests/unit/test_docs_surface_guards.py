"""Docs-surface guards wired into ``build_about_content.py --lint``.

Each lint has a synthetic positive / negative case plus a "the real repo is
clean" gate, so the lint cannot rot into a no-op and a doc regression fails
here without a KG:

- ``lint_brief_sections``          every brief tool page carries What it does /
                                   Parameters / Example / Response sketch /
                                   Common mistakes / chaining (or the
                                   overflow marker) / the ``/full`` pointer.
- ``lint_index_size``              ``docs://index`` stays under
                                   ``INDEX_MAX_CHARS``.
- ``lint_kg_claims_quoted``        every ``kg_claims.yaml`` entry names the
                                   text it pins (``quoted``) and that text
                                   appears in each ``used_in`` file.
- ``lint_example_tocs``            the ``(line ~N)`` pointers in the
                                   ``# CONTENTS`` block of each example script
                                   land on the scenario's ``def``.
- ``lint_outfacing_identifiers``   backtick identifiers and ``tool(param=)``
                                   keywords in hand-authored docs name real
                                   params / fields / KG names.
- ``lint_hierarchy_flat_claims``   no prose calls a hierarchical ontology flat
                                   (registry-driven from ``ONTOLOGY_CONFIG``).
- read-when overrides              ``docs://index`` rows use the hand-written
                                   routing note where the first sentence is a
                                   poor hint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import build_about_content as bac

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def tool_schemas():
    return bac.get_tool_schemas()


# ---------------------------------------------------------------------------
# Brief-page sections
# ---------------------------------------------------------------------------

_GOOD_BRIEF = """# t

## What it does

x

## Parameters

x

## Example

x

## Response sketch

x

## Common mistakes

- x

## Chaining patterns

- x

Full reference: `docs://tools/t/full`
"""


def test_brief_sections_accepts_a_complete_page(tmp_path):
    p = tmp_path / "t.md"
    p.write_text(_GOOD_BRIEF)
    assert bac.lint_brief_sections([p]) == []


def test_brief_sections_accepts_the_chaining_overflow_marker(tmp_path):
    p = tmp_path / "t.md"
    p.write_text(_GOOD_BRIEF.replace(
        "## Chaining patterns\n\n- x\n",
        "Chaining patterns: see `docs://tools/t/full`.\n"))
    assert bac.lint_brief_sections([p]) == []


@pytest.mark.parametrize("drop", [
    "## Example\n\nx\n\n",
    "## Response sketch\n\nx\n\n",
    "## Common mistakes\n\n- x\n\n",
    "## Chaining patterns\n\n- x\n\n",
])
def test_brief_sections_flags_a_missing_section(tmp_path, drop):
    p = tmp_path / "t.md"
    p.write_text(_GOOD_BRIEF.replace(drop, ""))
    out = bac.lint_brief_sections([p])
    assert len(out) == 1 and out[0].startswith("t:"), out


def test_brief_sections_flags_a_missing_full_pointer(tmp_path):
    p = tmp_path / "t.md"
    p.write_text(_GOOD_BRIEF.replace("`docs://tools/t/full`", "the full page"))
    assert bac.lint_brief_sections([p])


def test_every_brief_page_carries_all_sections():
    assert bac.lint_brief_sections(sorted(bac.OUTPUT_DIR.glob("*.md"))) == []


# ---------------------------------------------------------------------------
# Index size
# ---------------------------------------------------------------------------

def test_index_size_flags_an_oversized_index(tmp_path):
    p = tmp_path / "index.md"
    p.write_text("x" * (bac.INDEX_MAX_CHARS + 1))
    assert bac.lint_index_size(p)


def test_index_size_accepts_the_cap(tmp_path):
    p = tmp_path / "index.md"
    p.write_text("x" * bac.INDEX_MAX_CHARS)
    assert bac.lint_index_size(p) == []


def test_served_index_within_cap():
    assert bac.lint_index_size() == []


# ---------------------------------------------------------------------------
# kg_claims `quoted` content check
# ---------------------------------------------------------------------------

def test_kg_claims_quoted_flags_a_file_missing_the_text(tmp_path):
    (tmp_path / "a.md").write_text("About 71% of numeric\nedges are tested-absent.\n")
    (tmp_path / "b.md").write_text("Nothing numeric here.\n")
    claims = [{"id": "c", "quoted": ["71% of numeric edges"], "used_in": ["a.md", "b.md"]}]
    out = bac.lint_kg_claims_quoted(claims, repo=tmp_path)
    assert len(out) == 1 and "b.md" in out[0], out


def test_kg_claims_quoted_any_variant_matches(tmp_path):
    (tmp_path / "a.md").write_text("on only 11 of 34 boolean DMs\n")
    claims = [{"id": "c", "quoted": ["11 of 34", "eleven"], "used_in": ["a.md"]}]
    assert bac.lint_kg_claims_quoted(claims, repo=tmp_path) == []


def test_kg_claims_quoted_is_required(tmp_path):
    (tmp_path / "a.md").write_text("x\n")
    out = bac.lint_kg_claims_quoted([{"id": "c", "used_in": ["a.md"]}], repo=tmp_path)
    assert out and "quoted" in out[0]


def test_kg_claims_quoted_text_appears_in_every_used_in_file():
    assert bac.lint_kg_claims_quoted() == []


# ---------------------------------------------------------------------------
# Example-script CONTENTS line pins
# ---------------------------------------------------------------------------

_TOC_SCRIPT = '''"""Doc."""
# CONTENTS
#   1. scenario_a  — first (line ~6)
#   2. scenario_b  — second (line ~{b})


def scenario_a() -> None:
    pass


def scenario_b() -> None:
    pass
'''


def test_example_toc_accepts_accurate_pins(tmp_path):
    p = tmp_path / "x.py"
    p.write_text(_TOC_SCRIPT.format(b=11))
    assert bac.lint_example_tocs([p]) == []


def test_example_toc_flags_a_drifted_pin(tmp_path):
    p = tmp_path / "x.py"
    p.write_text(_TOC_SCRIPT.format(b=40))
    out = bac.lint_example_tocs([p])
    assert len(out) == 1 and "scenario_b" in out[0], out


def test_example_toc_flags_a_missing_scenario(tmp_path):
    p = tmp_path / "x.py"
    p.write_text(_TOC_SCRIPT.format(b=11).replace("def scenario_b", "def scenario_c"))
    out = bac.lint_example_tocs([p])
    assert len(out) == 1 and "scenario_b" in out[0], out


def test_example_toc_pins_match_the_scripts():
    assert bac.lint_example_tocs() == []


# ---------------------------------------------------------------------------
# VerboseParam names the /full page (verbose_fields live only there)
# ---------------------------------------------------------------------------

def test_verbose_param_points_at_the_full_page():
    from multiomics_explorer.mcp_server.params import VerboseParam

    description = VerboseParam.__metadata__[0].description
    assert "docs://tools/{tool}/full" in description, description


# ---------------------------------------------------------------------------
# Outfacing identifiers
# ---------------------------------------------------------------------------

def test_identifier_lint_flags_an_unknown_backtick_identifier(tmp_path, tool_schemas):
    p = tmp_path / "x.md"
    p.write_text("Read `zzq_not_a_real_field` on every row; `locus_tags` is fine.\n")
    out = bac.lint_outfacing_identifiers(tool_schemas, paths=[p])
    assert len(out) == 1 and "zzq_not_a_real_field" in out[0], out


def test_identifier_lint_flags_an_unknown_tool_kwarg(tmp_path, tool_schemas):
    p = tmp_path / "x.md"
    p.write_text("Call resolve_gene(identifier='dnaN', zzq_bogus=1) first.\n")
    out = bac.lint_outfacing_identifiers(tool_schemas, paths=[p])
    assert len(out) == 1 and "resolve_gene(zzq_bogus=" in out[0], out


def test_identifier_lint_ignores_wrong_side_of_a_mistake(tmp_path, tool_schemas):
    p = tmp_path / "x.yaml"
    p.write_text(
        "mistakes:\n"
        "  - wrong: \"resolve_gene(zzq_bogus=1)  # `zzq_not_a_param` is no param\"\n"
        "    right: resolve_gene(identifier='dnaN')\n"
    )
    assert bac.lint_outfacing_identifiers(tool_schemas, paths=[p]) == []


def test_identifier_lint_skips_yaml_examples(tmp_path, tool_schemas):
    p = tmp_path / "x.yaml"
    p.write_text(
        "examples:\n"
        "  - title: t\n"
        "    call: resolve_gene(identifier='dnaN')\n"
        "    response: |\n"
        "      {\"zzq_not_a_real_field\": 1}  `zzq_other_thing`\n"
        "mistakes:\n"
        "  - \"`zzq_after_examples` is unknown\"\n"
    )
    out = bac.lint_outfacing_identifiers(tool_schemas, paths=[p])
    assert len(out) == 1 and "zzq_after_examples" in out[0], out


def test_identifier_lint_ignores_tool_definitions(tmp_path, tool_schemas):
    p = tmp_path / "tools.py"
    p.write_text("async def resolve_gene(\n    zzq_internal: int = 1,\n):\n    pass\n")
    assert bac.lint_outfacing_identifiers(tool_schemas, paths=[p]) == []


def test_identifier_allowlist_is_well_formed():
    entries = bac.load_identifier_allowlist(raw=True)
    seen: set[str] = set()
    for entry in entries:
        assert set(entry) == {"tokens", "reason"}, entry
        assert entry["reason"].strip(), entry
        for tok in entry["tokens"]:
            assert tok not in seen, f"duplicate allowlist token {tok}"
            seen.add(tok)


def test_hand_authored_docs_name_real_identifiers(tool_schemas):
    out = bac.lint_outfacing_identifiers(tool_schemas)
    assert out == [], "\n".join(out)


# ---------------------------------------------------------------------------
# Hierarchical ontologies are never called flat
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "CAZy is a flat ontology.",
    "Distinct CAZy families on this gene (Gene.cazy_family_count; flat ontology).",
    "TCDB is flat, so `level=1` returns nothing.",
    "For pfam, `level=1` returns nothing.",
])
def test_flat_lint_flags_a_hierarchical_ontology(tmp_path, text):
    p = tmp_path / "x.md"
    p.write_text(text + "\n")
    assert bac.lint_hierarchy_flat_claims([p]), text


@pytest.mark.parametrize("text", [
    "COG and NCBIfam are flat — `level=1` returns nothing for them. Pfam clans are level 0.",
    "PSORTb, SignalP, COG and NCBIfam are flat.",
    "CAZy is not flat: families roll up into classes.",
    "`not_found` is a flat list on genes_by_ontology.",
    "Flat ontologies (`cog_category`, `ncbifam`) have only `level=0`; InterPro rolls up.",
])
def test_flat_lint_accepts_flat_ontologies_and_other_flats(tmp_path, text):
    p = tmp_path / "x.md"
    p.write_text(text + "\n")
    assert bac.lint_hierarchy_flat_claims([p]) == [], text


def test_flat_lint_reads_an_ontology_yaml_as_its_own_key(tmp_path):
    hier = tmp_path / "cazy.yaml"
    hier.write_text("hierarchy: |\n  Flat: every family is level 0.\n")
    flat = tmp_path / "ncbifam.yaml"
    flat.write_text("hierarchy: |\n  Flat: every family is level 0.\n")
    assert bac.lint_hierarchy_flat_claims([hier])
    assert bac.lint_hierarchy_flat_claims([flat]) == []


def test_no_doc_calls_a_hierarchical_ontology_flat():
    out = bac.lint_hierarchy_flat_claims()
    assert out == [], "\n".join(out)


# ---------------------------------------------------------------------------
# docs://index read-when overrides
# ---------------------------------------------------------------------------

def test_read_when_overrides_name_indexed_uris():
    index = bac.render_docs_index()
    for uri in bac.READ_WHEN_OVERRIDES:
        assert f"`{uri}`" in index, uri


def test_read_when_overrides_are_short_single_sentences():
    for uri, note in bac.READ_WHEN_OVERRIDES.items():
        assert len(note) <= 110, uri
        assert note.endswith("."), uri


def test_index_rows_use_the_override():
    index = bac._render_docs_index_at(110)
    for uri, note in bac.READ_WHEN_OVERRIDES.items():
        row = next(line for line in index.splitlines() if f"`{uri}`" in line)
        assert row.endswith(note), (uri, row)


def test_read_when_overrides_cover_the_weak_first_sentences():
    for uri in (
        "docs://guide/start_here",
        "docs://guide/python_api",
        "docs://examples/metabolites.py",
        "docs://examples/pathway_enrichment.py",
    ):
        assert uri in bac.READ_WHEN_OVERRIDES, uri
