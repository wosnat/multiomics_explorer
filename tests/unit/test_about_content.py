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
