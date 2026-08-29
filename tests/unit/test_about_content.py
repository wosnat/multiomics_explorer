"""Tests for generated about-content consistency with tool schemas.

Verifies that:
- Every tool with a Pydantic response model has an about file
- expected-keys in about files match actual response model fields
- Parameter names in about files match tool parameter schema
- example-call blocks reference valid tool names
"""

import asyncio
import re
from pathlib import Path

import pytest

from multiomics_explorer.mcp_server.tools import register_tools

ABOUT_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "multiomics_explorer" / "skills" / "multiomics-kg-guide" / "references" / "tools"
)


@pytest.fixture(scope="module")
def tool_schemas():
    """Extract schemas from all registered tools."""
    from fastmcp import FastMCP

    mcp = FastMCP("test")
    register_tools(mcp)

    async def _extract():
        tools = await mcp.list_tools()
        schemas = {}
        for t in tools:
            tool = await mcp.get_tool(t.name)
            mcp_tool = tool.to_mcp_tool()
            schemas[t.name] = {
                "description": mcp_tool.description or "",
                "parameters": mcp_tool.inputSchema,
                "output_schema": mcp_tool.outputSchema,
            }
        return schemas

    return asyncio.run(_extract())


def _get_about_files() -> list[Path]:
    """Return all about markdown files."""
    if not ABOUT_DIR.exists():
        return []
    return sorted(ABOUT_DIR.glob("*.md"))


def _extract_expected_keys(content: str) -> list[str]:
    """Extract keys from ```expected-keys blocks."""
    pattern = r"```expected-keys\n(.+?)\n```"
    matches = re.findall(pattern, content, re.DOTALL)
    keys = []
    for match in matches:
        keys.extend(k.strip() for k in match.split(","))
    return keys


def _extract_example_calls(content: str) -> list[str]:
    """Extract tool names from ```example-call blocks."""
    pattern = r"```example-call\n(.+?)\n```"
    matches = re.findall(pattern, content, re.DOTALL)
    names = []
    for match in matches:
        # Extract function name from call like "list_publications(organism='MED4')"
        m = re.match(r"(\w+)\(", match.strip())
        if m:
            names.append(m.group(1))
    return names


def _extract_param_names_from_about(content: str) -> list[str]:
    """Extract parameter names from the Parameters table."""
    # Match rows like "| organism | string \| None | None | description |"
    pattern = r"^\| (\w+) \|"
    names = []
    in_table = False
    for line in content.split("\n"):
        if "| Name |" in line:
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and line.startswith("| "):
            m = re.match(pattern, line)
            if m:
                names.append(m.group(1))
        elif in_table and not line.startswith("|"):
            in_table = False
    return names


# --- Drift guards: validate call kwargs and tool-count claims against the live
#     registry, across the hand-authored YAML inputs and guide/analysis docs
#     (the generated tool md is already covered by TestAboutContentConsistency). ---

_ROOT = Path(__file__).resolve().parent.parent.parent
_INPUTS_DIR = _ROOT / "multiomics_explorer" / "inputs" / "tools"
_GUIDE_DIR = (
    _ROOT / "multiomics_explorer" / "skills" / "multiomics-kg-guide"
    / "references" / "guide"
)
_ANALYSIS_DIR = (
    _ROOT / "multiomics_explorer" / "skills" / "multiomics-kg-guide"
    / "references" / "analysis"
)
_CLAUDE_MD = _ROOT / "CLAUDE.md"
_SERVER_PY = _ROOT / "multiomics_explorer" / "mcp_server" / "server.py"

# Kwargs valid in Python-package call examples but absent from MCP tool schemas
# (the package functions take a connection; the MCP layer injects it).
_NON_MCP_KWARGS = {"conn"}


def _top_level_kwargs(arg: str) -> list[str]:
    """Names of top-level `name=` kwargs in a call's argument string."""
    parts, cur, depth = [], "", 0
    for ch in arg:
        if ch in "([{":
            depth += 1
            cur += ch
        elif ch in ")]}":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    names = []
    for p in parts:
        m = re.match(r"\s*([A-Za-z_]\w*)\s*=(?!=)", p)
        if m:
            names.append(m.group(1))
    return names


def _iter_tool_calls(text: str, tool_names: set[str]):
    """Yield (tool_name, [kwarg, ...]) for each `name(...)` whose name is a tool."""
    for m in re.finditer(r"\b([a-z_][a-z0-9_]*)\(", text):
        name = m.group(1)
        if name not in tool_names:
            continue
        i = m.end() - 1
        depth, j = 0, i
        while j < len(text):
            ch = text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield name, _top_level_kwargs(text[i + 1 : j])


def test_yaml_example_kwargs_valid(tool_schemas):
    """Kwargs in YAML example/steps/chaining calls are real params.

    `mistakes:` is excluded — it deliberately contains wrong calls.
    """
    import yaml

    tool_names = set(tool_schemas)
    failures = []
    for yf in sorted(_INPUTS_DIR.glob("*.yaml")):
        data = yaml.safe_load(yf.read_text()) or {}
        texts: list[str] = []
        for ex in data.get("examples") or []:
            texts.append(str(ex.get("call") or ""))
            texts.append(str(ex.get("steps") or ""))
        for c in data.get("chaining") or []:
            if isinstance(c, str):
                texts.append(c)
        for text in texts:
            for name, kwargs in _iter_tool_calls(text, tool_names):
                params = set(
                    (tool_schemas[name]["parameters"].get("properties") or {})
                ) | _NON_MCP_KWARGS
                for kw in kwargs:
                    if kw not in params:
                        failures.append(f"{yf.name}: {name}(... {kw}=...) is not a param")
    assert not failures, "Stale example-call kwargs:\n" + "\n".join(failures)


def test_guide_and_analysis_kwargs_valid(tool_schemas):
    """Tool calls in guide/ and analysis/ docs use real params (`conn` allowed)."""
    tool_names = set(tool_schemas)
    failures = []
    for doc_dir in (_GUIDE_DIR, _ANALYSIS_DIR):
        for md in sorted(doc_dir.glob("*.md")):
            for name, kwargs in _iter_tool_calls(md.read_text(), tool_names):
                params = set(
                    (tool_schemas[name]["parameters"].get("properties") or {})
                ) | _NON_MCP_KWARGS
                for kw in kwargs:
                    if kw not in params:
                        failures.append(
                            f"{md.parent.name}/{md.name}: {name}(... {kw}=...) is not a param"
                        )
    assert not failures, "Stale doc-call kwargs:\n" + "\n".join(failures)


def test_every_tool_has_yaml_doc_and_claude_row(tool_schemas):
    """Each registered tool has a YAML input, a generated doc, and a CLAUDE.md row
    — and there are no orphan YAML/doc files for nonexistent tools."""
    tool_names = set(tool_schemas)
    yaml_stems = {p.stem for p in _INPUTS_DIR.glob("*.yaml")}
    doc_stems = {p.stem for p in _get_about_files()}
    claude_rows = set(re.findall(r"^\| `([a-z_]+)` \|", _CLAUDE_MD.read_text(), re.M))

    problems = []
    for t in sorted(tool_names):
        if t not in yaml_stems:
            problems.append(f"{t}: missing inputs/tools/{t}.yaml")
        if t not in doc_stems:
            problems.append(f"{t}: missing references/tools/{t}.md")
        if t not in claude_rows:
            problems.append(f"{t}: missing CLAUDE.md tool-table row")
    for orphan in sorted(yaml_stems - tool_names):
        problems.append(f"orphan YAML for unregistered tool: {orphan}")
    for orphan in sorted(doc_stems - tool_names):
        problems.append(f"orphan doc for unregistered tool: {orphan}")
    assert not problems, "Tool/doc registry drift:\n" + "\n".join(problems)


def test_tool_count_claims_match_registry(tool_schemas):
    """Hard-coded 'N tools' / 'X of N tools accept summary' claims in guide docs and
    the server instructions stay in sync with the live registry."""
    total = len(tool_schemas)
    with_summary = sum(
        1
        for s in tool_schemas.values()
        if "summary" in (s["parameters"].get("properties") or {})
    )
    without_summary = total - with_summary
    valid_before_tools = {total, without_summary}

    failures = []
    for f in list(_GUIDE_DIR.glob("*.md")) + [_SERVER_PY]:
        text = f.read_text()
        for n in re.findall(r"(\d+)\s+tools\b", text):
            if int(n) not in valid_before_tools:
                failures.append(
                    f"{f.name}: '{n} tools' — expected one of "
                    f"{sorted(valid_before_tools)} (total / without-summary)"
                )
        for x in re.findall(r"(\d+)\s+of\s+\d+\s+tools", text):
            if int(x) != with_summary:
                failures.append(
                    f"{f.name}: '{x} of N tools' — expected {with_summary} "
                    "(tools accepting summary=)"
                )
    assert not failures, "Tool-count claim drift:\n" + "\n".join(failures)


def test_python_returns_override():
    """When YAML carries `python_returns: <Class>`, the package-import
    block emits an object-shape example, not `returns dict`. B2 #5."""
    from scripts.build_about_content import _build_package_import_section

    section = _build_package_import_section(
        tool_name="pathway_enrichment",
        params=[
            {"name": "organism", "default": "—"},
            {"name": "experiment_ids", "default": "—"},
        ],
        envelope=[{"name": "results"}],
        has_results=True,
        python_returns="EnrichmentResult",
    )
    text = "\n".join(section)
    assert "returns dict" not in text
    assert "EnrichmentResult" in text
    assert ".to_envelope(" in text
    # Without an explicit example URL, no example pointer is emitted.
    assert "docs://examples/" not in text


def test_python_returns_default_unchanged():
    """When `python_returns` absent, fall back to the existing
    `returns dict with keys` behavior."""
    from scripts.build_about_content import _build_package_import_section

    section = _build_package_import_section(
        tool_name="list_organisms",
        params=[],
        envelope=[{"name": "total_matching"}, {"name": "results"}],
        has_results=True,
        python_returns=None,
    )
    text = "\n".join(section)
    assert "returns dict with keys" in text


def test_python_returns_example_pointer_emitted():
    """When both `python_returns` and `python_returns_example` are set,
    the section appends a `See <example>` line. Decoupled from any
    specific example URL — works for any class. B2 #5 follow-up."""
    from scripts.build_about_content import _build_package_import_section

    section = _build_package_import_section(
        tool_name="pathway_enrichment",
        params=[],
        envelope=[{"name": "results"}],
        has_results=True,
        python_returns="EnrichmentResult",
        python_returns_example="docs://examples/pathway_enrichment.py",
    )
    text = "\n".join(section)
    assert "docs://examples/pathway_enrichment.py" in text
    assert "See " in text


def test_python_returns_example_omitted_without_python_returns():
    """An example pointer alone (without `python_returns`) does NOT
    appear — the dict-returning path emits envelope keys only."""
    from scripts.build_about_content import _build_package_import_section

    section = _build_package_import_section(
        tool_name="list_organisms",
        params=[],
        envelope=[{"name": "results"}],
        has_results=True,
        python_returns=None,
        python_returns_example="docs://examples/whatever.py",
    )
    text = "\n".join(section)
    assert "whatever.py" not in text


def test_response_notes_renders_subsection():
    """When YAML provides response_notes:, build_about_content.py
    renders them as a subsection under Response format. B2 #6."""
    from scripts.build_about_content import _build_response_notes_section

    section = _build_response_notes_section([
        {"title": "Cluster naming",
         "body": "Cluster IDs are `{experiment_id}|{timepoint}|{direction}`. NaN timepoints render as `\"NA\"`."},
    ])
    text = "\n".join(section)
    assert "### Cluster naming" in text
    assert "experiment_id" in text
    assert "NA" in text


def test_response_notes_empty_list():
    """No response_notes → empty section list."""
    from scripts.build_about_content import _build_response_notes_section
    assert _build_response_notes_section([]) == []
    assert _build_response_notes_section(None) == []


class TestAboutContentConsistency:
    """Verify about files are consistent with tool schemas."""

    def test_about_files_reference_valid_tools(self, tool_schemas):
        """Every about file name matches a registered tool."""
        for path in _get_about_files():
            tool_name = path.stem
            assert tool_name in tool_schemas, (
                f"About file '{path.name}' does not match any registered tool. "
                f"Registered: {sorted(tool_schemas)}"
            )

    def test_example_calls_reference_valid_tools(self, tool_schemas):
        """example-call blocks reference registered tool names."""
        for path in _get_about_files():
            content = path.read_text()
            call_names = _extract_example_calls(content)
            for name in call_names:
                assert name in tool_schemas, (
                    f"About file '{path.name}' has example-call for "
                    f"'{name}' which is not a registered tool"
                )

    def test_expected_keys_match_response_envelope(self, tool_schemas):
        """expected-keys include the always-present response envelope fields.

        Conditional envelope keys (e.g. `evidence_score_signals`, emitted only
        when `min_evidence_score` is set) are excluded from the generated
        expected-keys block, so the gate skips exactly the same set. Imported
        from the generator rather than duplicated — single source of truth.
        """
        from scripts.build_about_content import CONDITIONAL_ENVELOPE_KEYS

        for path in _get_about_files():
            tool_name = path.stem
            schema = tool_schemas.get(tool_name)
            if not schema or not schema.get("output_schema"):
                continue

            content = path.read_text()
            expected_keys = _extract_expected_keys(content)
            if not expected_keys:
                continue

            # Check envelope fields are in expected-keys
            output_props = schema["output_schema"].get("properties", {})
            for prop_name in output_props:
                if prop_name in CONDITIONAL_ENVELOPE_KEYS:
                    continue
                assert prop_name in expected_keys, (
                    f"About file '{path.name}': response field '{prop_name}' "
                    f"missing from expected-keys"
                )

    def test_param_names_match_tool_schema(self, tool_schemas):
        """Parameter names in about file match tool input schema."""
        for path in _get_about_files():
            tool_name = path.stem
            schema = tool_schemas.get(tool_name)
            if not schema:
                continue

            content = path.read_text()
            about_params = set(_extract_param_names_from_about(content))
            if not about_params:
                continue

            schema_params = set(schema["parameters"].get("properties", {}).keys())
            assert about_params == schema_params, (
                f"About file '{path.name}': param mismatch.\n"
                f"  In about but not schema: {about_params - schema_params}\n"
                f"  In schema but not about: {schema_params - about_params}"
            )


@pytest.mark.parametrize(
    "about_path",
    _get_about_files(),
    ids=lambda p: p.stem,
)
def test_about_content_lint_clean(about_path):
    """Each tool's rendered md passes the outfacing-doc readability lint.

    Catches reintroductions of time-stamped counts, internal-history
    shorthand (§, parent §, Phase N, audit, KG-XXX-NNN, Mode-X,
    Cluster X), and bare ISO date stamps. [AQ] / [ENR] drift markers
    are exempt.
    """
    from scripts.build_about_content import lint_about_content

    violations = lint_about_content([about_path])
    if violations:
        snippets = "\n".join(
            f"  line {ln}: {tok!r} | {line.strip()[:120]}"
            for _, ln, line, tok in violations[:10]
        )
        more = (
            f"\n  ... {len(violations) - 10} more"
            if len(violations) > 10
            else ""
        )
        pytest.fail(
            f"{len(violations)} outfacing-doc style violation(s) in "
            f"{about_path.name}:\n{snippets}{more}\n"
            "See docs/superpowers/specs/"
            "2026-05-07-mcp-docs-readability-pass-design.md"
        )



# ---------------------------------------------------------------------------
# PR 3b: per-ontology reference docs — the `ontologies` generator stage
# (design §9). 17 hand-authored yaml inputs -> references/ontologies/{key}.md
# + index.md, served at docs://ontologies/{key}. No Neo4j required to build.
# ---------------------------------------------------------------------------

import yaml as _yaml3b

from multiomics_explorer._outfacing_lint import lint_lines as _lint_lines3b
from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG as _CFG3B

_ONTOLOGY_INPUTS_DIR = _ROOT / "multiomics_explorer" / "inputs" / "ontologies"
_ONTOLOGY_DOCS_DIR = (
    _ROOT / "multiomics_explorer" / "skills" / "multiomics-kg-guide"
    / "references" / "ontologies"
)
_ONTOLOGY_KEYS = list(_CFG3B)
_ONTOLOGY_YAML_KEYS = [
    "what_it_is", "method", "id_form", "hierarchy", "interpretation",
    "informativeness_rule", "pitfalls", "typical_questions", "see_also",
]
_BASELINE_PATH3B = _ROOT / "multiomics_explorer" / "config" / "schema_baseline.yaml"


def _ontology_yaml(key):
    path = _ONTOLOGY_INPUTS_DIR / f"{key}.yaml"
    assert path.exists(), f"missing {path}"
    return _yaml3b.safe_load(path.read_text()) or {}


def _ontology_md(key):
    path = _ONTOLOGY_DOCS_DIR / f"{key}.md"
    assert path.exists(), f"missing {path}"
    return path.read_text()


class TestOntologyReferenceInputs:
    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    def test_yaml_exists(self, key):
        assert (_ONTOLOGY_INPUTS_DIR / f"{key}.yaml").exists()

    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    @pytest.mark.parametrize("field", _ONTOLOGY_YAML_KEYS)
    def test_yaml_required_field(self, key, field):
        data = _ontology_yaml(key)
        assert field in data, f"{key}.yaml lacks {field}"
        assert data[field], f"{key}.yaml: {field} is empty"

    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    def test_typical_questions_is_a_list(self, key):
        assert isinstance(_ontology_yaml(key)["typical_questions"], list)

    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    def test_see_also_is_a_list_of_docs_links(self, key):
        see_also = _ontology_yaml(key)["see_also"]
        assert isinstance(see_also, list) and see_also
        for link in see_also:
            assert str(link).startswith("docs://"), link

    def test_no_stray_inputs(self):
        stems = {p.stem for p in _ONTOLOGY_INPUTS_DIR.glob("*.yaml")}
        assert stems == set(_ONTOLOGY_KEYS)


class TestOntologyReferenceDocs:
    def test_docs_dir_exists(self):
        assert _ONTOLOGY_DOCS_DIR.is_dir()

    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    def test_md_exists(self, key):
        assert (_ONTOLOGY_DOCS_DIR / f"{key}.md").exists()

    def test_index_exists_and_links_every_key(self):
        index = (_ONTOLOGY_DOCS_DIR / "index.md").read_text()
        for key in _ONTOLOGY_KEYS:
            assert key in index, f"index.md does not mention {key}"

    def test_no_stray_docs(self):
        stems = {p.stem for p in _ONTOLOGY_DOCS_DIR.glob("*.md")}
        assert stems == set(_ONTOLOGY_KEYS) | {"index"}

    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    def test_md_merges_the_registry_row(self, key):
        """Label, gene_rel, hierarchy rels and bridges come from
        ONTOLOGY_CONFIG at build time — never hand-typed."""
        md = _ontology_md(key)
        cfg = _CFG3B[key]
        assert cfg["label"] in md
        assert cfg["gene_rel"] in md
        for rel in cfg["hierarchy_rels"]:
            assert rel in md, rel
        for rel, target, kind in cfg.get("bridges_out") or []:
            assert rel in md, rel
            assert kind in md, kind

    @pytest.mark.parametrize("key", [
        k for k in _ONTOLOGY_KEYS if (_CFG3B[k].get("trust") or {})
    ])
    def test_md_lists_the_trust_axes(self, key):
        md = _ontology_md(key)
        for axis in ("sources", "evidence", "evidence_score", "tier"):
            if axis in (_CFG3B[key].get("trust") or {}):
                assert axis in md, axis

    @pytest.mark.parametrize("key", ["brite", "interpro"])
    def test_md_names_the_facet(self, key):
        assert _CFG3B[key]["facet"]["param"] in _ontology_md(key)

    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    def test_md_carries_the_human_sections(self, key):
        md = _ontology_md(key)
        data = _ontology_yaml(key)
        for question in data["typical_questions"]:
            assert str(question).strip()[:30] in md, question
        for link in data["see_also"]:
            assert str(link) in md, link

    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    def test_md_names_baseline_node_props(self, key):
        """Schema-baseline node props for the label are rendered."""
        baseline = _yaml3b.safe_load(_BASELINE_PATH3B.read_text())["schema"]
        props = set(baseline["nodes"].get(_CFG3B[key]["label"], {})
                    .get("properties", {}))
        md = _ontology_md(key)
        missing = [p for p in props if p not in md]
        assert not missing, f"{key}.md lacks node props {missing}"

    @pytest.mark.parametrize("key", _ONTOLOGY_KEYS)
    def test_md_points_at_the_term_tools(self, key):
        md = _ontology_md(key)
        assert "ontology_term_details" in md
        assert "search_ontology" in md

    @pytest.mark.parametrize(
        "md_path",
        sorted(_ONTOLOGY_DOCS_DIR.glob("*.md")) if _ONTOLOGY_DOCS_DIR.exists() else [],
        ids=lambda p: p.stem,
    )
    def test_md_lint_clean(self, md_path):
        violations = _lint_lines3b([md_path])
        assert not violations, [
            f"{p.name}:{n}: {tok!r} in: {line.strip()}"
            for p, n, line, tok in violations]

    def test_lint_matrix_is_not_vacuous(self):
        assert len(list(_ONTOLOGY_DOCS_DIR.glob("*.md"))) == 18


class TestOntologiesGeneratorStage:
    """`scripts/build_about_content.py` grows an `ontologies` stage that
    renders without a live KG (vocabulary values fall back to a pointer at
    `list_filter_values`)."""

    def test_module_exposes_the_stage_dirs(self):
        from scripts import build_about_content as gen
        assert gen.ONTOLOGY_INPUTS_DIR == _ONTOLOGY_INPUTS_DIR
        assert gen.ONTOLOGY_OUTPUT_DIR == _ONTOLOGY_DOCS_DIR

    def test_render_ontology_without_kg(self):
        from scripts.build_about_content import render_ontology
        data = {
            "what_it_is": "Transporter classification.",
            "method": "HMM + curated.",
            "id_form": "tcdb:3.A.1",
            "hierarchy": "5 levels.",
            "interpretation": "Rank by evidence_score.",
            "informativeness_rule": "Roots are uninformative.",
            "pitfalls": "Superseded attachments.",
            "typical_questions": ["Which ABC transporters does MED4 carry?"],
            "see_also": ["docs://analysis/metabolites"],
        }
        out = render_ontology("tcdb", data, vocab_values=None)
        assert "TcdbFamily" in out
        assert "Gene_has_tcdb_family" in out
        assert "Tcdb_family_is_a_tcdb_family" in out
        assert "Tcdb_family_has_pfam_domain" in out
        assert "composition" in out
        assert "Which ABC transporters does MED4 carry?" in out
        assert "docs://analysis/metabolites" in out
        assert "list_filter_values" in out

    def test_render_ontology_with_vocab_values(self):
        from scripts.build_about_content import render_ontology
        data = {k: "x" for k in _ONTOLOGY_YAML_KEYS}
        data["typical_questions"] = ["q"]
        data["see_also"] = ["docs://guide/concepts"]
        out = render_ontology(
            "merops", data,
            vocab_values={"call_class": ["peptidase", "nonpeptidase_homolog"]})
        assert "nonpeptidase_homolog" in out

    def test_render_ontology_index_lists_every_key(self):
        from scripts.build_about_content import render_ontology_index
        inputs = {k: {"what_it_is": f"about {k}"} for k in _ONTOLOGY_KEYS}
        out = render_ontology_index(inputs)
        for key in _ONTOLOGY_KEYS:
            assert key in out

    def test_index_summary_ends_at_a_sentence_or_word_boundary(self):
        """Summaries never cut mid-word or mid-line: each ends with `.`
        (first sentence) or `…` (cut at a word boundary before ~110 chars),
        and hard-wrapped YAML lines are re-joined before the cut."""
        from scripts.build_about_content import _summary_sentence, render_ontology_index
        short = "Pfam protein domain families and clans.\nSecond sentence here."
        assert _summary_sentence(short) == "Pfam protein domain families and clans."
        wrapped = ("Gene Ontology biological process — the branch of GO (e.g.\n"
                   "`go:0006979` response to oxidative stress) that describes\n"
                   "what larger program a gene is part of. Second sentence.")
        out = _summary_sentence(wrapped)
        assert out.endswith("…") and len(out) <= 111
        assert "\n" not in out and not out.endswith("(e.g.…")
        assert out.split("…")[0].rsplit(" ", 1)[-1] in wrapped.replace("\n", " ")
        assert _summary_sentence("Short (e.g. this). More.") == "Short (e.g. this)."
        inputs = {k: {"what_it_is": "x " * 80 + "y. tail"} for k in _ONTOLOGY_KEYS}
        for line in render_ontology_index(inputs).splitlines():
            if line.startswith("| `"):
                summary = line.rsplit("|", 2)[-2].strip()
                assert summary.endswith(".") or summary.endswith("…"), summary

    def test_lint_covers_the_ontologies_dir(self):
        src = (_ROOT / "scripts" / "build_about_content.py").read_text()
        assert 'skills_refs / "ontologies"' in src

    def test_cli_accepts_the_ontologies_stage(self):
        src = (_ROOT / "scripts" / "build_about_content.py").read_text()
        assert "--ontologies" in src or '"ontologies"' in src


# ---------------------------------------------------------------------------
# Docs-review generator fixes: package-import key list, union type rendering,
# one "Common mistakes" heading, illustrative examples, ontology prop notes,
# applicable filter types + index columns, example-response envelope lint.
# ---------------------------------------------------------------------------


def test_package_import_lists_returned_and_truncated():
    """The Python API returns the full MCP envelope (`returned` / `truncated`
    included) — the package-import block must not strip them."""
    from scripts.build_about_content import _build_package_import_section

    section = "\n".join(_build_package_import_section(
        tool_name="resolve_gene",
        params=[{"name": "identifier", "default": "—"}],
        envelope=[{"name": "total_matching"}, {"name": "returned"},
                  {"name": "truncated"}, {"name": "offset"}],
        has_results=True,
    ))
    assert "returns dict with keys: total_matching, returned, truncated, offset, results" in section
    assert "subset" not in section


def test_type_string_renders_every_union_arm():
    from scripts.build_about_content import _type_string

    prop = {"anyOf": [{"type": "string"},
                      {"type": "array", "items": {"type": "string"}},
                      {"type": "null"}]}
    assert _type_string(prop) == "string | list[string] | None"
    assert _type_string({"anyOf": [{"type": "integer"}, {"type": "number"}]}) == "int | float"
    assert _type_string({"anyOf": [{"type": "integer"}, {"type": "null"}]}) == "int | None"
    assert _type_string({"anyOf": [{"type": "null"}]}) == "any | None"


def test_generated_union_param_shows_scalar_arm(tool_schemas):
    from scripts.build_about_content import extract_params_table

    rows = {r["name"]: r for r in extract_params_table(tool_schemas["search_ontology"])}
    assert rows["ontology"]["type"] == "string | list[string] | None"


def test_mistakes_heading_is_always_common_mistakes():
    from scripts.build_about_content import render_about

    schema = {"description": "d", "parameters": {"properties": {}}, "output_schema": None}
    plain = render_about("t", schema, {"mistakes": ["only a note"]})
    assert "## Common mistakes" in plain
    assert "Good to know" not in plain
    assert "- only a note" in plain
    pairs = render_about("t", schema, {"mistakes": [{"wrong": "w", "right": "r"}]})
    assert "## Common mistakes" in pairs
    assert "```mistake\nw\n```" in pairs


def test_example_illustrative_marker_and_note():
    from scripts.build_about_content import render_about

    schema = {"description": "d", "parameters": {"properties": {}}, "output_schema": None}
    md = render_about("t", schema, {"examples": [
        {"title": "Hand-written", "call": "t()", "illustrative": True,
         "note": "Shape only; IDs are made up.", "response": "{}"},
        {"title": "Live", "call": "t()", "response": "{}"},
    ]})
    assert "### Example 1: Hand-written (illustrative — not a live response)" in md
    assert "*Shape only; IDs are made up.*" in md
    assert "### Example 2: Live\n" in md
    # The note sits under the call, before the response block.
    assert md.index("```example-call") < md.index("*Shape only") < md.index("```example-response")


def test_example_keys_lint_accepts_illustrative_and_note():
    from scripts.build_about_content import EXAMPLE_KEYS, lint_example_keys

    assert {"title", "call", "response", "steps", "illustrative", "note"} <= EXAMPLE_KEYS
    ok = {"examples": [{"title": "x", "call": "t()", "illustrative": True, "note": "n"}]}
    assert lint_example_keys("t", ok) == []
    bad = {"examples": [{"title": "x", "call": "t()", "ilustrative": True}]}
    assert any("ilustrative" in v for v in lint_example_keys("t", bad))


def test_yaml_example_keys_are_known():
    """Every example entry across inputs/tools/*.yaml uses only known keys."""
    from scripts.build_about_content import lint_example_keys

    failures = []
    for yf in sorted(_INPUTS_DIR.glob("*.yaml")):
        failures += lint_example_keys(yf.stem, _yaml3b.safe_load(yf.read_text()) or {})
    assert not failures, "\n".join(failures)


def test_node_prop_notes_cover_every_ontology_label_prop():
    """Every baseline prop on an ontology (or parent) label has a one-liner."""
    from scripts.build_about_content import _NODE_PROP_NOTES

    baseline = _yaml3b.safe_load(_BASELINE_PATH3B.read_text())["schema"]["nodes"]
    missing = []
    for key, cfg in _CFG3B.items():
        for label in [cfg["label"]] + ([cfg["parent_label"]] if cfg.get("parent_label") else []):
            for prop in (baseline.get(label) or {}).get("properties") or {}:
                if not _NODE_PROP_NOTES.get(prop):
                    missing.append(f"{key}/{label}.{prop}")
    assert not missing, "blank Meaning cells: " + ", ".join(missing)


def test_ontology_page_lists_applicable_filter_types():
    from scripts.build_about_content import applicable_filter_types, render_ontology

    assert applicable_filter_types("merops") == [
        "evidence", "sources", "call_class", "link_kinds"]
    assert applicable_filter_types("interpro") == [
        "evidence", "sources", "interpro_type", "link_kinds"]
    assert applicable_filter_types("ncbifam") == [
        "evidence", "sources", "ncbifam_family_type", "link_kinds"]
    assert applicable_filter_types("tcdb") == [
        "evidence", "sources", "attachment_depth", "link_kinds"]
    assert applicable_filter_types("brite") == ["evidence", "sources", "brite_tree"]
    assert applicable_filter_types("subcellular_localization") == []

    data = {k: "x" for k in _ONTOLOGY_YAML_KEYS}
    data["typical_questions"] = ["q"]
    data["see_also"] = ["docs://guide/concepts"]
    md = render_ontology("merops", data)
    assert "## Applicable filter types" in md
    assert "## Controlled vocabularies" not in md
    assert "`list_filter_values(filter_type=\"call_class\", ontology=\"merops\")`" in md
    assert "`list_filter_values(filter_type=\"link_kinds\")`" in md
    assert "read live" in md
    flat = render_ontology("subcellular_localization", data)
    assert "## Applicable filter types" in flat
    assert "none" in flat.split("## Applicable filter types")[1].split("##")[0]


def test_ontology_index_has_levels_hierarchy_trust_columns():
    from scripts.build_about_content import render_ontology_index

    inputs = {k: {"what_it_is": f"about {k}."} for k in _ONTOLOGY_KEYS}
    out = render_ontology_index(inputs)
    assert "controlled vocabularies" not in out.split("\n")[2]
    header = next(line for line in out.splitlines() if line.startswith("| key |"))
    assert "| Levels |" in header and "| Hierarchy |" in header and "| Trust |" in header
    rows = {line.split("|")[1].strip("` "): line for line in out.splitlines() if line.startswith("| `")}
    assert "| 0–11 | DAG | yes |" in rows["go_bp"]
    assert "| 0–4 | tree | yes |" in rows["tcdb"]
    assert "| 0 | flat | no |" in rows["subcellular_localization"]
    assert "| 0–1 | tree | yes |" in rows["pfam"]


def test_lint_example_response_requires_envelope_key():
    from scripts.build_about_content import lint_example_responses

    schema = {"output_schema": {"properties": {"total_matching": {}, "results": {}}}}
    good = {"examples": [{"title": "a", "call": "t()", "response": '{"total_matching": 1}'}]}
    assert lint_example_responses("t", good, schema) == []
    bad = {"examples": [{"title": "b", "call": "t()", "response": '{"gene_count": 1973}'}]}
    v = lint_example_responses("t", bad, schema)
    assert len(v) == 1 and "b" in v[0]
    # No response block, no output schema -> nothing to check.
    assert lint_example_responses("t", {"examples": [{"title": "c", "call": "t()"}]}, schema) == []
    assert lint_example_responses("t", bad, {"output_schema": None}) == []


def test_yaml_example_responses_carry_an_envelope_key(tool_schemas):
    from scripts.build_about_content import lint_example_responses

    failures = []
    for yf in sorted(_INPUTS_DIR.glob("*.yaml")):
        if yf.stem in tool_schemas:
            failures += lint_example_responses(
                yf.stem, _yaml3b.safe_load(yf.read_text()) or {}, tool_schemas[yf.stem])
    assert not failures, "\n".join(failures)
