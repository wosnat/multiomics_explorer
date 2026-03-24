#!/usr/bin/env python3
"""Build about-content markdown for MCP tools.

Merges auto-extracted Pydantic schema data with human-authored input
YAML files to produce per-tool about pages served via MCP resource.

Usage:
    uv run python scripts/build_about_content.py                  # all tools with input files
    uv run python scripts/build_about_content.py list_publications # specific tool
    uv run python scripts/build_about_content.py --skeleton search_genes  # generate input YAML skeleton
"""

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

# Paths
INPUTS_DIR = Path(__file__).resolve().parent.parent / "multiomics_explorer" / "inputs" / "tools"
OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "multiomics_explorer" / "skills" / "multiomics-kg-guide" / "references" / "tools"
)


def get_tool_schemas() -> dict:
    """Extract tool schemas from registered FastMCP tools.

    Returns {tool_name: {"description", "parameters", "output_schema"}}.
    """
    from fastmcp import FastMCP

    from multiomics_explorer.mcp_server.tools import register_tools

    mcp = FastMCP("build")
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


def extract_params_table(schema: dict) -> list[dict]:
    """Extract parameter rows from input schema."""
    props = schema.get("parameters", {}).get("properties", {})
    required = set(schema.get("parameters", {}).get("required", []))
    rows = []
    for name, prop in props.items():
        if name in ("ctx",):
            continue
        type_str = _type_string(prop)
        default = prop.get("default", "—")
        if default is None:
            default = "None"
        desc = prop.get("description", "")
        rows.append({
            "name": name,
            "type": type_str,
            "default": str(default),
            "description": desc,
        })
    return rows
    return rows


def _type_string(prop: dict) -> str:
    """Convert JSON Schema property to readable type string."""
    if "anyOf" in prop:
        types = [_type_string(t) for t in prop["anyOf"] if t.get("type") != "null"]
        nullable = any(t.get("type") == "null" for t in prop["anyOf"])
        base = types[0] if types else "any"
        return f"{base} | None" if nullable else base
    # Handle $ref to named model (e.g. {"$ref": "#/$defs/OrganismBreakdown"})
    if "$ref" in prop:
        ref = prop["$ref"]
        return ref.rsplit("/", 1)[-1]
    # Handle enum (Literal types) — show as the base type
    if "enum" in prop:
        t = prop.get("type", "string")
        vals = ", ".join(f"'{v}'" for v in prop["enum"])
        return f"{t} ({vals})"
    t = prop.get("type", "any")
    if t == "array":
        items = prop.get("items", {})
        item_type = _type_string(items)
        return f"list[{item_type}]"
    if t == "integer":
        return "int"
    if t == "number":
        return "float"
    if t == "boolean":
        return "bool"
    return t


def extract_response_fields(schema: dict) -> tuple[list[dict], list[dict]]:
    """Extract envelope fields and per-result fields from output schema.

    Returns (envelope_fields, result_fields).
    """
    output = schema.get("output_schema")
    if not output:
        return [], []

    envelope = []
    result_fields = []

    props = output.get("properties", {})
    for name, prop in props.items():
        if name == "results":
            # Extract per-result fields from $ref
            ref = prop.get("items", {}).get("$ref", "")
            if ref:
                def_name = ref.split("/")[-1]
                defs = output.get("$defs", {})
                result_def = defs.get(def_name, {})
                result_props = result_def.get("properties", {})
                result_required = set(result_def.get("required", []))
                for rname, rprop in result_props.items():
                    result_fields.append({
                        "name": rname,
                        "type": _type_string(rprop),
                        "description": rprop.get("description", ""),
                        "required": rname in result_required,
                    })
        else:
            envelope.append({
                "name": name,
                "type": _type_string(prop),
                "description": prop.get("description", ""),
            })

    return envelope, result_fields


def render_about(tool_name: str, schema: dict, input_data: dict | None) -> str:
    """Render the about markdown for a tool."""
    lines = []

    # Header
    lines.append(f"# {tool_name}")
    lines.append("")

    # What it does
    lines.append("## What it does")
    lines.append("")
    lines.append(schema["description"])
    lines.append("")

    # Parameters (auto-generated)
    params = extract_params_table(schema)
    lines.append("## Parameters")
    lines.append("")
    lines.append("| Name | Type | Default | Description |")
    lines.append("|---|---|---|---|")
    for p in params:
        type_escaped = p['type'].replace('|', '\\|')
        lines.append(f"| {p['name']} | {type_escaped} | {p['default']} | {p['description']} |")
    lines.append("")
    # Discovery hints — only for tools with relevant filter params
    param_names = {p["name"] for p in params}
    has_organism = "organism" in param_names
    has_category = "category" in param_names or "treatment_type" in param_names
    if has_organism or has_category:
        hints = []
        if has_category:
            hints.append("`list_filter_values` for valid filter values")
        if has_organism:
            hints.append("`list_organisms` for valid organism names")
        lines.append(f"**Discovery:** use {', '.join(hints)}.")
        lines.append("")

    # Response format (auto-generated)
    envelope, result_fields = extract_response_fields(schema)
    lines.append("## Response format")
    lines.append("")

    if envelope:
        lines.append("### Envelope")
        lines.append("")
        lines.append("```expected-keys")
        suffix = ", results" if result_fields else ""
        lines.append(", ".join(f["name"] for f in envelope) + suffix)
        lines.append("```")
        lines.append("")
        for f in envelope:
            if f["description"]:
                lines.append(f"- **{f['name']}** ({f['type']}): {f['description']}")
            else:
                lines.append(f"- **{f['name']}** ({f['type']})")
        lines.append("")

    if result_fields:
        verbose_fields = set(
            (input_data or {}).get("verbose_fields", [])
        )
        compact = [f for f in result_fields if f["name"] not in verbose_fields]
        verbose = [f for f in result_fields if f["name"] in verbose_fields]

        lines.append("### Per-result fields")
        lines.append("")
        lines.append("| Field | Type | Description |")
        lines.append("|---|---|---|")
        for f in compact:
            req = "" if f["required"] else " (optional)"
            desc = f["description"] or ""
            type_escaped = f["type"].replace("|", "\\|")
            lines.append(f"| {f['name']} | {type_escaped}{req} | {desc} |")
        lines.append("")

        if verbose:
            lines.append("**Verbose-only fields** (included when `verbose=True`):")
            lines.append("")
            lines.append("| Field | Type | Description |")
            lines.append("|---|---|---|")
            for f in verbose:
                req = "" if f["required"] else " (optional)"
                desc = f["description"] or ""
                type_escaped = f["type"].replace("|", "\\|")
                lines.append(f"| {f['name']} | {type_escaped}{req} | {desc} |")
            lines.append("")

    # Few-shot examples (from input YAML)
    if input_data and input_data.get("examples"):
        lines.append("## Few-shot examples")
        lines.append("")
        for i, ex in enumerate(input_data["examples"], 1):
            lines.append(f"### Example {i}: {ex['title']}")
            lines.append("")
            if "call" in ex:
                lines.append("```example-call")
                lines.append(ex["call"])
                lines.append("```")
                lines.append("")
            if "response" in ex:
                lines.append("```example-response")
                lines.append(ex["response"].rstrip())
                lines.append("```")
                lines.append("")
            if "steps" in ex:
                lines.append("```")
                lines.append(ex["steps"].rstrip())
                lines.append("```")
                lines.append("")
    else:
        lines.append("## Few-shot examples")
        lines.append("")
        lines.append("<!-- TODO: Add examples -->")
        lines.append("")

    # Chaining patterns (from input YAML)
    if input_data and input_data.get("chaining"):
        lines.append("## Chaining patterns")
        lines.append("")
        lines.append("```")
        for c in input_data["chaining"]:
            lines.append(c)
        lines.append("```")
        lines.append("")
    else:
        lines.append("## Chaining patterns")
        lines.append("")
        lines.append("<!-- TODO: Add chaining patterns -->")
        lines.append("")

    # Common mistakes (from input YAML)
    # Supports two formats:
    #   - plain string: rendered as a note/gotcha
    #   - dict with wrong/right: rendered as mistake/correction pair
    if input_data and input_data.get("mistakes"):
        # Use "Good to know" if all entries are plain strings (notes/gotchas),
        # "Common mistakes" if any are wrong/right pairs
        has_pairs = any(isinstance(m, dict) for m in input_data["mistakes"])
        heading = "Common mistakes" if has_pairs else "Good to know"
        lines.append(f"## {heading}")
        lines.append("")
        for m in input_data["mistakes"]:
            if isinstance(m, str):
                lines.append(f"- {m}")
                lines.append("")
            else:
                lines.append("```mistake")
                lines.append(m["wrong"])
                lines.append("```")
                lines.append("")
                lines.append("```correction")
                lines.append(m["right"])
                lines.append("```")
                lines.append("")

    # Package import (auto-generated)
    lines.append("## Package import equivalent")
    lines.append("")
    lines.append("```python")
    lines.append(f"from multiomics_explorer import {tool_name}")
    lines.append("")
    # Build example call with required params
    required_params = [p for p in params if p["default"] == "—"]
    if required_params:
        example_args = ", ".join(
            f'{p["name"]}=...' for p in required_params
        )
        lines.append(f'result = {tool_name}({example_args})')
    else:
        lines.append(f'result = {tool_name}()')
    # API returns a subset of the MCP envelope (no returned/truncated wrapper)
    api_keys = [f["name"] for f in envelope if f["name"] not in ("returned", "truncated")]
    if result_fields:
        api_keys.append("results")
    envelope_keys = ", ".join(api_keys)
    lines.append(f'# returns dict with keys: {envelope_keys}')
    lines.append("```")
    lines.append("")
    lines.append("Use package import for bulk data extraction in scripts.")
    lines.append("Use MCP for reasoning and interactive exploration.")
    lines.append("")

    return "\n".join(lines)


def generate_skeleton(tool_name: str, schema: dict) -> str:
    """Generate input YAML skeleton for a tool."""
    # Check if tool has a verbose param
    has_verbose = any(
        p.get("name") == "verbose"
        for p in schema.get("parameters", {}).get("properties", {}).values()
    ) or "verbose" in schema.get("parameters", {}).get("properties", {})

    lines = [
        f"# Human-authored content for {tool_name} about page.",
        "# Auto-generated sections (params, response format, expected-keys)",
        "# come from Pydantic models via scripts/build_about_content.py.",
        "",
        "examples:",
        "  - title: Basic usage",
        f"    call: {tool_name}()",
        "    # response: |",
        "    #   {{ ... }}",
        "",
        "  # - title: With filters",
        f"  #   call: {tool_name}(param=\"value\")",
        "",
        "  # - title: Chaining workflow",
        "  #   steps: |",
        "  #     Step 1: ...",
        "  #     Step 2: ...",
        "",
    ]

    if has_verbose:
        lines += [
            "# Fields only returned with verbose=True.",
            "# Splits per-result table into compact + verbose sections.",
            "verbose_fields: []",
            "  # - field_name",
            "",
        ]

    lines += [
        "chaining:",
        f'  # - "{tool_name} → next_tool"',
        "",
        "# Plain strings → 'Good to know' section.",
        "# Dicts with wrong/right → 'Common mistakes' section.",
        "mistakes: []",
        "  # - \"plain note about this tool\"",
        "  # - wrong: \"common mistake\"",
        "  #   right: \"correct approach\"",
        "",
    ]
    return "\n".join(lines)


def build_tool(tool_name: str, schemas: dict) -> bool:
    """Build about content for a single tool. Returns True if successful."""
    if tool_name not in schemas:
        print(f"  SKIP {tool_name}: not a registered tool")
        return False

    schema = schemas[tool_name]
    input_path = INPUTS_DIR / f"{tool_name}.yaml"
    output_path = OUTPUT_DIR / f"{tool_name}.md"

    input_data = None
    if input_path.exists():
        input_data = yaml.safe_load(input_path.read_text())

    markdown = render_about(tool_name, schema, input_data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)

    status = "built" if input_data else "built (no input YAML — TODOs remain)"
    print(f"  OK   {tool_name}: {output_path.relative_to(Path.cwd())} [{status}]")
    return True


def main():
    parser = argparse.ArgumentParser(description="Build about-content for MCP tools")
    parser.add_argument("tools", nargs="*", help="Tool names to build (default: all with input files)")
    parser.add_argument("--skeleton", metavar="TOOL", help="Generate input YAML skeleton for a tool")
    parser.add_argument("--all", action="store_true", help="Build for all registered tools")
    args = parser.parse_args()

    if args.skeleton:
        schemas = get_tool_schemas()
        if args.skeleton not in schemas:
            print(f"Error: '{args.skeleton}' is not a registered tool")
            print(f"Available: {sorted(schemas)}")
            sys.exit(1)
        skeleton = generate_skeleton(args.skeleton, schemas[args.skeleton])
        out_path = INPUTS_DIR / f"{args.skeleton}.yaml"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists():
            print(f"Error: {out_path} already exists. Delete it first to regenerate.")
            sys.exit(1)
        out_path.write_text(skeleton)
        print(f"Generated skeleton: {out_path.relative_to(Path.cwd())}")
        return

    print("Extracting tool schemas...")
    schemas = get_tool_schemas()
    print(f"Found {len(schemas)} registered tools")
    print()

    if args.all:
        tool_names = sorted(schemas.keys())
    elif args.tools:
        tool_names = args.tools
    else:
        # Default: all tools that have input YAML files
        tool_names = sorted(p.stem for p in INPUTS_DIR.glob("*.yaml") if p.stem in schemas)

    if not tool_names:
        print("No tools to build. Use --all or specify tool names.")
        print(f"Tools with input files: {sorted(p.stem for p in INPUTS_DIR.glob('*.yaml'))}")
        print(f"Registered tools: {sorted(schemas)}")
        sys.exit(1)

    print(f"Building about content for {len(tool_names)} tools:")
    ok = 0
    for name in tool_names:
        if build_tool(name, schemas):
            ok += 1
    print(f"\nDone: {ok}/{len(tool_names)} built")


if __name__ == "__main__":
    main()
