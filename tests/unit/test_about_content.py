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
        """expected-keys include the response envelope fields."""
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
