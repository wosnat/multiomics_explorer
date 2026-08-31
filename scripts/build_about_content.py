#!/usr/bin/env python3
"""Build about-content markdown for MCP tools.

Merges auto-extracted Pydantic schema data with human-authored input
YAML files to produce per-tool about pages served via MCP resource.

Output: writes directly to
``multiomics_explorer/skills/multiomics-kg-guide/references/tools/{tool}.md``
(the brief page, no separate sync step — that path is served) and
``multiomics_explorer/skills/multiomics-kg-guide/references/tools/full/{tool}.md``
(the full page, unchanged content of the historical single-page render).

Usage:
    uv run python scripts/build_about_content.py                  # all tools with input files
    uv run python scripts/build_about_content.py list_publications # specific tool
    uv run python scripts/build_about_content.py --skeleton search_genes  # generate input YAML skeleton
    uv run python scripts/build_about_content.py --ontologies        # per-ontology reference only

The default / ``--all`` build also runs the ``ontologies`` stage: 17
hand-authored ``inputs/ontologies/{key}.yaml`` files (keys =
``ONTOLOGY_CONFIG`` keys) are merged with the registry row, the
``config/schema_baseline.yaml`` node properties and — when a KG is
reachable — the ``ControlledVocabulary`` values, into
``references/ontologies/{key}.md`` + ``index.md`` (served at
``docs://ontologies/{key}``). No Neo4j is required to build.

Supported YAML keys (in ``multiomics_explorer/inputs/tools/{tool}.yaml``):

| Key                       | Type                          | Renders as                                              |
|---------------------------|-------------------------------|---------------------------------------------------------|
| ``examples``              | list[{title, call, response, steps, illustrative, note}] | "Few-shot examples" section; ``illustrative: true`` marks the title "(illustrative — not a live response)", ``note`` renders italic under the call |
| ``verbose_fields``        | list[str]                     | Splits per-result table into compact + verbose          |
| ``chaining``              | list[str]                     | "Chaining patterns" section                             |
| ``mistakes``              | list (str or {wrong, right})  | "Common mistakes" section (bullets and/or wrong/right pairs) |
| ``response_notes``        | list[{title, body}]           | Subsections under "Response format"                     |
| ``python_returns``        | str (class name)              | Replaces "returns dict with keys" with object-shape hint|
| ``python_returns_example``| str (URI)                     | Appends a `See <uri>` line (only when python_returns set)|

Auto-generated sections (params table, response format, envelope keys) are
extracted from Pydantic models in ``mcp_server/tools.py``.
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

import yaml

from multiomics_explorer._outfacing_lint import (  # noqa: F401 — re-exported for tests/unit
    CARVEOUT_PATTERN,
    LINT_PATTERN,
    lint_about_content,
    lint_lines,
    lint_python_docstrings,
    run_lint,
)

# Paths
INPUTS_DIR = Path(__file__).resolve().parent.parent / "multiomics_explorer" / "inputs" / "tools"
OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "multiomics_explorer" / "skills" / "multiomics-kg-guide" / "references" / "tools"
)
# Full-length pages (unchanged content of the historical single-page render)
# live one level down; OUTPUT_DIR itself now holds the default brief pages.
FULL_OUTPUT_DIR = OUTPUT_DIR / "full"

# Brief page hard cap (llm-review 2b.4 D2). `render_brief` trims
# deterministically (chaining first, then mistakes beyond the first) to
# stay under this before returning.
BRIEF_MAX_CHARS = 8000

ONTOLOGY_INPUTS_DIR = (
    Path(__file__).resolve().parent.parent / "multiomics_explorer" / "inputs" / "ontologies"
)
ONTOLOGY_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent
    / "multiomics_explorer" / "skills" / "multiomics-kg-guide" / "references" / "ontologies"
)
SCHEMA_BASELINE_PATH = (
    Path(__file__).resolve().parent.parent
    / "multiomics_explorer" / "config" / "schema_baseline.yaml"
)

# Envelope fields that are declared on the Pydantic response model but are
# NOT unconditionally present in every response dict — they appear only
# under a specific caller-set condition (e.g. a filter param being passed).
# The ```expected-keys block documents keys a caller can rely on seeing on
# every call; conditional keys are still documented via their bullet
# description in the "Envelope" section, just excluded from that block, so
# the integration smoke test (tests/integration/test_about_examples.py)
# doesn't demand them on examples that don't trigger the condition.
#
# evidence_score_signals: present only when `min_evidence_score` is set —
# pinned by tests/unit/test_api_functions.py::TestGenesByOntologyTrustEnvelope.
#
# `*_truncated` (llm-review 2b.2 `_cap_breakdowns`): sparse bool, present
# only when the corresponding breakdown list was actually capped at 10 on a
# detail call (absent/None on `summary=True` and on any call whose list
# doesn't exceed 10) — never demanded by the examples/expected-keys gate.
CONDITIONAL_ENVELOPE_KEYS = {
    "evidence_score_signals",
    "by_publication_truncated",
    "by_metric_type_truncated",
    "by_organism_truncated",
    "by_treatment_type_truncated",
    "by_background_factors_truncated",
    "top_annotation_capability_truncated",
    "top_metabolic_capability_truncated",
    "top_metabolite_pathways_truncated",
    "by_element_truncated",
    "top_genes_truncated",
    "top_reactions_truncated",
    "top_tcdb_families_truncated",
    "experiments_truncated",
    "by_experiment_truncated",
}


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
            ret = tool.fn.__annotations__.get("return")
            output_schema = ret.model_json_schema() if ret is not None and hasattr(ret, "model_json_schema") else None
            schemas[t.name] = {
                "description": mcp_tool.description or "",
                "parameters": mcp_tool.inputSchema,
                "output_schema": output_schema,
            }
        return schemas

    return asyncio.run(_extract())


def extract_params_table(schema: dict) -> list[dict]:
    """Extract parameter rows from input schema."""
    props = schema.get("parameters", {}).get("properties", {})
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
        # Render every non-null arm (`str | list[str] | None` must not
        # collapse to `list[string] | None`); `None` always goes last.
        arms: list[str] = []
        for arm in prop["anyOf"]:
            if arm.get("type") == "null":
                continue
            rendered = _type_string(arm)
            if rendered not in arms:
                arms.append(rendered)
        nullable = any(t.get("type") == "null" for t in prop["anyOf"])
        # Scalar arms before container arms: `string | list[string]` reads
        # as "pass one or many", whichever order the annotation declares.
        arms.sort(key=lambda a: a.startswith("list["))
        base = " | ".join(arms) if arms else "any"
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
            # Extract per-result fields from $ref (typed model).
            # For untyped list[dict], ref is absent — results still exists.
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


def _params_section(schema: dict) -> list[str]:
    """Parameters table + Discovery hint block, auto-generated from the input
    schema. Shared verbatim by `render_about` (full page) and `render_brief`
    (brief page) — do not duplicate this logic in either renderer."""
    params = extract_params_table(schema)
    lines: list[str] = []
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
    has_category = (
        "category" in param_names
        or "gene_categories" in param_names
        or "treatment_type" in param_names
    )
    if has_organism or has_category:
        hints = []
        if has_category:
            hints.append("`list_filter_values` for valid filter values")
        if has_organism:
            hints.append("`list_organisms` for valid organism names")
        lines.append(f"**Discovery:** use {', '.join(hints)}.")
        lines.append("")
    return lines


def _render_mistake(m) -> list[str]:
    """Render one `mistakes:` YAML entry.

    Supports both shapes used across `inputs/tools/*.yaml`: a plain string
    (rendered as a bullet) or a `{wrong, right}` dict (rendered as a
    mistake/correction code-block pair). Shared by `render_about` and
    `render_brief` so the brief's trimmed slice renders identically to the
    full page's, just with fewer entries.
    """
    if isinstance(m, str):
        return [f"- {m}", ""]
    return [
        "```mistake",
        m["wrong"],
        "```",
        "",
        "```correction",
        m["right"],
        "```",
        "",
    ]


def render_about(tool_name: str, schema: dict, input_data: dict | None) -> str:
    """Render the FULL about markdown for a tool (all examples, full response
    format, verbose fields, every mistake/chaining entry). Written to
    `FULL_OUTPUT_DIR/{tool_name}.md`, served at `docs://tools/{tool_name}/full`.
    """
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
    lines += _params_section(schema)

    # Response format (auto-generated)
    envelope, result_fields = extract_response_fields(schema)
    has_results = bool(result_fields) or "results" in (
        (schema.get("output_schema") or {}).get("properties") or {}
    )
    lines.append("## Response format")
    lines.append("")

    if envelope:
        lines.append("### Envelope")
        lines.append("")
        lines.append("```expected-keys")
        suffix = ", results" if has_results else ""
        always_present = [f["name"] for f in envelope if f["name"] not in CONDITIONAL_ENVELOPE_KEYS]
        lines.append(", ".join(always_present) + suffix)
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

    # Response notes (subsections under Response format, from input YAML)
    lines.extend(_build_response_notes_section((input_data or {}).get("response_notes")))

    # Few-shot examples (from input YAML)
    if input_data and input_data.get("examples"):
        lines.append("## Few-shot examples")
        lines.append("")
        for i, ex in enumerate(input_data["examples"], 1):
            title = ex["title"]
            if ex.get("illustrative"):
                title += ILLUSTRATIVE_MARKER
            lines.append(f"### Example {i}: {title}")
            lines.append("")
            if "call" in ex:
                lines.append("```example-call")
                lines.append(ex["call"])
                lines.append("```")
                lines.append("")
            if ex.get("note"):
                lines.append(f"*{str(ex['note']).strip()}*")
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
    # Supports two formats, under one fixed heading (readers grep for it):
    #   - plain string: rendered as a note/gotcha bullet
    #   - dict with wrong/right: rendered as mistake/correction pair
    if input_data and input_data.get("mistakes"):
        lines.append("## Common mistakes")
        lines.append("")
        for m in input_data["mistakes"]:
            lines.extend(_render_mistake(m))

    # Package import (auto-generated)
    lines.extend(_build_package_import_section(
        tool_name=tool_name,
        params=params,
        envelope=envelope,
        has_results=has_results,
        python_returns=(input_data or {}).get("python_returns"),
        python_returns_example=(input_data or {}).get("python_returns_example"),
    ))

    return "\n".join(lines)


def render_brief(tool_name: str, schema: dict, input_data: dict | None) -> str:
    """Render the BRIEF about markdown for a tool: what it does, params,
    one worked example, a response-shape sketch, the top few mistakes and
    chaining patterns, plus a pointer to the full page. Written to
    `OUTPUT_DIR/{tool_name}.md` (the default page), served at
    `docs://tools/{tool_name}`; the full page is `docs://tools/{tool_name}/full`.

    Deterministically trimmed to stay within `BRIEF_MAX_CHARS`: chaining
    drops first, then mistakes beyond the first.
    """
    header = [f"# {tool_name}", ""]
    header += ["## What it does", "", schema["description"], ""]
    header += _params_section(schema)

    examples = (input_data or {}).get("examples") or []
    example_section: list[str] = []
    if examples and "call" in examples[0]:
        ex = examples[0]
        example_section = [
            "## Example", "", f"### {ex['title']}", "",
            "```python", ex["call"].strip(), "```", "",
        ]

    envelope, result_fields = extract_response_fields(schema)
    # Same has_results fallback as render_about: an untyped `results: list[dict]`
    # (no $ref) yields no result_fields but still deserves the ", results" suffix.
    has_results = bool(result_fields) or "results" in (
        (schema.get("output_schema") or {}).get("properties") or {}
    )
    # The ```expected-keys fence holds only the envelope-keys line — same
    # contract as render_about's, so the shared `_extract_expected_keys`
    # test helper (a bare comma-split of the fenced block) parses it
    # correctly. The result-row summary is separate plain text below.
    response_section = ["## Response sketch", "", "```expected-keys"]
    always = [f["name"] for f in envelope if f["name"] not in CONDITIONAL_ENVELOPE_KEYS]
    response_section.append(", ".join(always) + (", results" if has_results else ""))
    response_section += ["```", ""]
    if result_fields:
        row = [f["name"] for f in result_fields][:12]
        more = "" if len(result_fields) <= 12 else ", …"
        response_section.append(f"Result row: `{', '.join(row)}{more}`")
        response_section.append("")

    all_mistakes = (input_data or {}).get("mistakes") or []
    chaining = (input_data or {}).get("chaining") or []

    pointer = [
        f"Full reference (all examples, full response format, verbose fields): "
        f"`docs://tools/{tool_name}/full`",
        "",
    ]

    def _tail(mistakes_slice: list, include_chaining: bool) -> list[str]:
        out: list[str] = []
        if mistakes_slice:
            out += ["## Common mistakes", ""]
            for m in mistakes_slice:
                out += _render_mistake(m)
        if include_chaining and chaining:
            out += ["## Chaining patterns", ""]
            out += [f"- {c}" for c in chaining]
            out += [""]
        return out

    base = header + example_section + response_section

    # Deterministic overflow trim, in order: full slate (<=3 mistakes +
    # chaining) -> drop chaining -> mistakes trimmed to just the first.
    for mistakes_slice, include_chaining in (
        (all_mistakes[:3], True),
        (all_mistakes[:3], False),
        (all_mistakes[:1], False),
    ):
        candidate = "\n".join(base + _tail(mistakes_slice, include_chaining) + pointer)
        if len(candidate) <= BRIEF_MAX_CHARS:
            return candidate

    # Still over budget with no chaining and at most one mistake — last
    # resort, drop mistakes too.
    return "\n".join(base + _tail([], False) + pointer)


def _build_response_notes_section(notes: list[dict] | None) -> list[str]:
    """Render YAML `response_notes` as subsections under Response format.

    Each note is `{"title": str, "body": str}`. Empty / None → no output.
    """
    if not notes:
        return []
    lines: list[str] = []
    for note in notes:
        lines.append(f"### {note['title']}")
        lines.append("")
        lines.append(note["body"])
        lines.append("")
    return lines


def _build_package_import_section(
    *,
    tool_name: str,
    params: list[dict],
    envelope: list[dict],
    has_results: bool,
    python_returns: str | None = None,
    python_returns_example: str | None = None,
) -> list[str]:
    """Render the 'Package import equivalent' section.

    When `python_returns` is set (e.g. "EnrichmentResult"), the example
    shows the object's accessors (`.results`, `.to_envelope(...)`)
    instead of asserting a dict return. Default behavior — `# returns
    dict with keys: ...` — preserved for the 20+ tools that do return
    dicts.

    When `python_returns_example` is set (e.g. "docs://examples/foo.py"),
    a `See <example>` line is appended pointing at the runnable resource.
    Independent of `python_returns` — but most useful when paired.
    """
    lines: list[str] = [
        "## Package import equivalent",
        "",
        "```python",
        f"from multiomics_explorer import {tool_name}",
        "",
    ]
    required_params = [p for p in params if p["default"] == "—"]
    args_str = ", ".join(f'{p["name"]}=...' for p in required_params)
    lines.append(
        f'result = {tool_name}({args_str})' if required_params
        else f'result = {tool_name}()'
    )

    if python_returns:
        lines.append(f'# returns {python_returns}; access result.results')
        lines.append('# and accessors. Call result.to_envelope() for the')
        lines.append('# MCP-equivalent dict shape.')
        if python_returns_example:
            lines.append(f'# See {python_returns_example} for runnable code.')
    else:
        # The API returns the same envelope dict the MCP tool serializes
        # (`returned` / `truncated` included).
        api_keys = [f["name"] for f in envelope]
        if has_results:
            api_keys.append("results")
        envelope_keys = ", ".join(api_keys)
        lines.append(f'# returns dict with keys: {envelope_keys}')

    lines.append("```")
    lines.append("")
    lines.append("Use package import for bulk data extraction in scripts.")
    lines.append("Use MCP for reasoning and interactive exploration.")
    lines.append("")
    return lines


ILLUSTRATIVE_MARKER = " (illustrative — not a live response)"

# Keys an `examples[]` entry may carry. `illustrative: true` = hand-written
# response (title gets ILLUSTRATIVE_MARKER; live-refresh tooling skips it);
# `note` = one italic line rendered under the call.
EXAMPLE_KEYS = frozenset({"title", "call", "response", "steps", "illustrative", "note"})


def lint_example_keys(tool_name: str, input_data: dict) -> list[str]:
    """Unknown keys on `examples[]` entries (typos silently render nothing)."""
    out: list[str] = []
    for i, ex in enumerate(input_data.get("examples") or [], 1):
        if not isinstance(ex, dict):
            out.append(f"{tool_name}.yaml: examples[{i}] is not a mapping")
            continue
        unknown = sorted(set(ex) - EXAMPLE_KEYS)
        if unknown:
            out.append(
                f"{tool_name}.yaml: examples[{i}] ({ex.get('title', '?')}) "
                f"has unknown keys {unknown}; allowed: {sorted(EXAMPLE_KEYS)}"
            )
    return out


_RESPONSE_KEY_RE = re.compile(r'(?:"|\b)([A-Za-z_][A-Za-z0-9_]*)"?\s*:')


def lint_example_responses(tool_name: str, input_data: dict, schema: dict) -> list[str]:
    """A YAML example `response` block must name at least one top-level
    envelope key of the tool's response model (`results` counts).

    Cheap sanity only — it catches pasted genome-wide stats or a response
    copied from another tool, not shape drift inside `results`.
    """
    output = (schema or {}).get("output_schema") or {}
    envelope_keys = set((output.get("properties") or {}))
    if not envelope_keys:
        return []
    out: list[str] = []
    for i, ex in enumerate(input_data.get("examples") or [], 1):
        if not isinstance(ex, dict) or not ex.get("response"):
            continue
        keys_in_block = set(_RESPONSE_KEY_RE.findall(str(ex["response"])))
        if not keys_in_block & envelope_keys:
            out.append(
                f"{tool_name}.yaml: examples[{i}] ({ex.get('title', '?')}) response "
                f"names none of the envelope keys {sorted(envelope_keys)}"
            )
    return out


def lint_example_yaml(schemas: dict) -> list[str]:
    """Run the example-entry lints over every `inputs/tools/*.yaml`."""
    out: list[str] = []
    for path in sorted(INPUTS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        out += lint_example_keys(path.stem, data)
        if path.stem in schemas:
            out += lint_example_responses(path.stem, data, schemas[path.stem])
    return out


DESCRIPTION_MAX_CHARS = 600  # ≈150 tokens; spec 2b.5 D2


def lint_description_length(schemas: dict) -> list[str]:
    """Flag tool descriptions that exceed the five-slot budget."""
    out = []
    for name, s in schemas.items():
        n = len(s.get("description") or "")
        if n > DESCRIPTION_MAX_CHARS:
            out.append(f"{name}: description {n} chars > {DESCRIPTION_MAX_CHARS}")
    return out


def lint_brief_size(paths: list[Path]) -> list[str]:
    """Flag brief pages (`OUTPUT_DIR/{name}.md`) over `BRIEF_MAX_CHARS`.

    `render_brief` trims deterministically before writing, so a violation
    here means the trim floor (one mistake, no chaining) still doesn't fit —
    a real problem with that tool's description/params/example, not
    something the generator can fix on its own.
    """
    out = []
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        n = len(text)
        if n > BRIEF_MAX_CHARS:
            out.append(f"{p.stem}: brief {n} chars > {BRIEF_MAX_CHARS}")
    return out


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
        "    # illustrative: true   # hand-written response, not captured live",
        "    # note: one italic line rendered under the call",
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
        "# All entries render under 'Common mistakes':",
        "# plain strings → bullets; dicts with wrong/right → mistake/correction pair.",
        "mistakes: []",
        "  # - \"plain note about this tool\"",
        "  # - wrong: \"common mistake\"",
        "  #   right: \"correct approach\"",
        "",
        "# Optional: subsections rendered under 'Response format'.",
        "# response_notes:",
        "#   - title: \"Cluster naming\"",
        "#     body: |",
        "#       Cluster IDs follow `{experiment_id}|{timepoint}|{direction}`.",
        "",
        "# Optional: when the Python entry point returns an object (not a",
        "# dict), declare the class name here. The 'Package import equivalent'",
        "# block then emits result.results / .to_envelope() hints instead of",
        "# 'returns dict with keys: ...'. Pair with python_returns_example",
        "# for a runnable-code pointer.",
        "# python_returns: SomeResultClass",
        "# python_returns_example: docs://examples/some_example.py",
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
    brief_path = OUTPUT_DIR / f"{tool_name}.md"
    full_path = FULL_OUTPUT_DIR / f"{tool_name}.md"

    input_data = None
    if input_path.exists():
        input_data = yaml.safe_load(input_path.read_text(encoding="utf-8"))

    full_markdown = render_about(tool_name, schema, input_data)
    brief_markdown = render_brief(tool_name, schema, input_data)

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(full_markdown, encoding="utf-8")
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text(brief_markdown, encoding="utf-8")

    status = "built" if input_data else "built (no input YAML — TODOs remain)"
    print(f"  OK   {tool_name}: {brief_path.relative_to(Path.cwd())} + full/{full_path.name} [{status}]")
    return True


# ---------------------------------------------------------------------------
# `ontologies` stage — per-ontology reference (docs://ontologies/{key})
# ---------------------------------------------------------------------------

ONTOLOGY_YAML_KEYS = (
    "what_it_is", "method", "id_form", "hierarchy", "interpretation",
    "informativeness_rule", "pitfalls", "typical_questions", "see_also",
)

# Human-readable names for the registry keys. Everything structural (label,
# edges, axes, facets, bridges) is read from ONTOLOGY_CONFIG at build time.
ONTOLOGY_DISPLAY_NAMES = {
    "go_bp": "GO biological process",
    "go_mf": "GO molecular function",
    "go_cc": "GO cellular component",
    "ec": "EC numbers",
    "kegg": "KEGG (categories, pathways, KOs)",
    "cog_category": "COG functional categories",
    "cyanorak_role": "Cyanorak roles",
    "tigr_role": "TIGR roles",
    "pfam": "Pfam domains and clans",
    "brite": "KEGG BRITE hierarchies",
    "tcdb": "TCDB transporter families",
    "cazy": "CAZy families",
    "subcellular_localization": "PSORTb subcellular localization",
    "signal_peptide_type": "SignalP signal-peptide type",
    "interpro": "InterPro entries",
    "ncbifam": "NCBIfam families",
    "merops": "MEROPS peptidase families",
}

# One-clause semantics for node props that recur across labels. Anything not
# listed renders with its baseline type only.
_NODE_PROP_NOTES = {
    "id": "term ID as used in `term_ids=[...]` (self-prefixed CURIE)",
    "preferred_id": "same value as `id`",
    "name": "term name (what `search_ontology` indexes)",
    "description": "longer free text (verbose on `search_ontology`; compact on `ontology_term_details`)",
    "level": "hierarchy depth, 0 = root / broadest",
    "level_kind": "what a level means in this ontology (e.g. `tc_family`, `pathway`) — read values via `list_filter_values`",
    "level_is_best_effort": "sparse `'true'` flag — DAG term whose depth is a min-path proxy",
    "gene_count": "genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones",
    "direct_gene_count": "genes attached to this exact node (not descendants); absent where it would be vacuous",
    "organism_count": "organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is)",
    "member_count": "upstream family size (source-database members), not KG genes",
    "ncbifam_family_count": "NCBIfam families bridged to this role via `Ncbifam_family_has_tigr_role`; subtree sum on mainroles",
    # --- per-ontology props (baseline labels) ---
    "code": "source-database short code (COG one-letter category, Cyanorak / TIGR numeric role code) — the un-prefixed tail of `id`",
    "alternate_name": "EC alternate enzyme name(s) from the source record",
    "catalytic_activity": "EC reaction text (substrates → products) from the source record",
    "comments": "EC free-text notes from the source record (transferred / deleted entries, caveats)",
    "short_name": "Pfam short name (e.g. `ABC_tran`); `name` holds the long description",
    "tree": "BRITE tree this category belongs to (snake_case, e.g. `transporters`) — the `tree=` facet value",
    "tree_code": "KEGG BRITE tree accession (e.g. `ko02000`) — the tree segment of `id`",
    "member_ko_count": "KOs listed under this BRITE category upstream (source membership, not KG genes)",
    "tcdb_id": "bare TC number (e.g. `3.A.1.14`); `id` is the `tcdb:` CURIE",
    "tc_class_id": "CURIE of the level-0 TC class this node sits under (e.g. `tcdb:3`) — for grouping without walking the hierarchy",
    "superfamily": "TCDB superfamily name the family belongs to, where TCDB assigns one (sparse)",
    "metabolite_count": "distinct substrates reachable via `Tcdb_family_transports_metabolite` (rolled up over the subtree, so it grows toward the root) — on KEGG, metabolites in the pathway",
    "cazy_id": "bare CAZy family code (e.g. `GH13`); `id` is the `cazy:` CURIE",
    "psortb_id": "PSORTb localization label as emitted by the tool (e.g. `CytoplasmicMembrane`)",
    "signalp_id": "SignalP signal-peptide type code as emitted by the tool (e.g. `SP`, `LIPO`, `TAT`)",
    "interpro_id": "bare InterPro accession (e.g. `IPR000001`); `id` is the `interpro:` CURIE",
    "interpro_type": "InterPro entry type (`FAMILY` / `DOMAIN` / `HOMOLOGOUS_SUPERFAMILY` / ...) — the `interpro_type=` facet value",
    "ncbifam_id": "bare NCBIfam / TIGRFAM accession (e.g. `TIGR00001`, `NF000001`); `id` is the `ncbifam:` CURIE",
    "family_type": "NCBIfam model type (equivalog, subfamily, domain, ...) — the `ncbifam_family_type` filter value",
    "gene_symbol": "gene symbol NCBIfam assigns to the family's members (sparse)",
    "merops_id": "bare MEROPS identifier (clan e.g. `SC`, family `S8`, subfamily `S8A`); `id` is the `merops.*:` CURIE",
    "family_class": "MEROPS grouping of the family (peptidase vs inhibitor family) — the `merops_family_class` filter value",
    "catalytic_type": "MEROPS catalytic type (serine, cysteine, metallo, ...) — the `merops_catalytic_type` filter value",
    "peptidase_gene_count": "genes attached with `call_class = 'peptidase'` (excludes nonpeptidase homologs); compare with `gene_count`",
    "peptidase_organism_count": "organisms with at least one `call_class = 'peptidase'` gene on the term",
    "cleavage_summary": "MEROPS cleavage-site specificity summary text (sparse; family level)",
    "cleavage_p1_residues": "residues MEROPS reports at the P1 cleavage position (sparse; family level)",
    "known_cleavage_count": "number of MEROPS-recorded cleavage sites behind the specificity summary (sparse)",
}


# Observed `level` range per ontology key (min, max), from the live KG.
# Static so the index renders without Neo4j; `--live-vocab` re-checks it
# against the reachable KG and warns on drift.
ONTOLOGY_LEVEL_RANGES: dict[str, tuple[int, int]] = {
    "go_bp": (0, 11), "go_mf": (0, 9), "go_cc": (0, 6),
    "ec": (0, 3), "kegg": (0, 3), "cog_category": (0, 0),
    "cyanorak_role": (0, 2), "tigr_role": (0, 1), "pfam": (0, 1),
    "brite": (0, 3), "tcdb": (0, 4), "cazy": (0, 1),
    "subcellular_localization": (0, 0), "signal_peptide_type": (0, 0),
    "interpro": (0, 2), "ncbifam": (0, 0), "merops": (0, 2),
}

# `list_filter_values` filter types owned by one ontology (rendered with
# `ontology=` scoping). Trust axes (`evidence` / `sources`) come from the
# registry's trust row; `link_kinds` applies wherever `bridges_out` is set.
_ONTOLOGY_OWNED_FILTER_TYPES: dict[str, list[str]] = {
    "merops": ["call_class"],
    "interpro": ["interpro_type"],
    "ncbifam": ["ncbifam_family_type"],
    "tcdb": ["attachment_depth"],
    "brite": ["brite_tree"],
}
_UNSCOPED_FILTER_TYPES = frozenset({"link_kinds", "brite_tree"})


def applicable_filter_types(key: str) -> list[str]:
    """`list_filter_values` filter types that apply to this ontology, in
    render order: trust axes, the ontology-owned categorical, `link_kinds`."""
    from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG, ontology_trust_axes

    cfg = ONTOLOGY_CONFIG[key]
    out: list[str] = []
    axes = set(ontology_trust_axes(key))
    if "evidence" in axes:
        out.append("evidence")
    if "sources" in axes:
        out.append("sources")
    out += _ONTOLOGY_OWNED_FILTER_TYPES.get(key, [])
    if cfg.get("bridges_out"):
        out.append("link_kinds")
    return out


def _hierarchy_kind(key: str, cfg: dict, baseline: dict | None = None) -> str:
    """`flat` (no hierarchy rels), `DAG` (baseline carries the
    `level_is_best_effort` min-path marker) or `tree`."""
    if not cfg.get("hierarchy_rels"):
        return "flat"
    props = _label_props(cfg["label"], baseline)
    return "DAG" if "level_is_best_effort" in props else "tree"


def _level_range_cell(key: str) -> str:
    lo, hi = ONTOLOGY_LEVEL_RANGES.get(key, (0, 0))
    return str(lo) if lo == hi else f"{lo}–{hi}"


def check_level_ranges_live() -> list[str]:
    """Compare ONTOLOGY_LEVEL_RANGES with a reachable KG; [] when unreachable."""
    from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG

    try:
        from multiomics_explorer.kg.connection import GraphConnection

        conn = GraphConnection()
        try:
            drift: list[str] = []
            for key, cfg in ONTOLOGY_CONFIG.items():
                labels = [cfg["label"]] + ([cfg["parent_label"]] if cfg.get("parent_label") else [])
                match = " UNION ALL ".join(
                    f"MATCH (t:{lab}) RETURN t.level AS level" for lab in labels
                )
                rows = conn.execute_query(
                    f"CALL {{ {match} }} RETURN min(level) AS mn, max(level) AS mx",
                    timeout=10,
                )
                live = (rows[0]["mn"], rows[0]["mx"])
                if live != ONTOLOGY_LEVEL_RANGES.get(key):
                    drift.append(f"{key}: static {ONTOLOGY_LEVEL_RANGES.get(key)} vs live {live}")
            return drift
        finally:
            conn.close()
    except Exception:
        return []


def _label_props(label: str, baseline: dict | None = None) -> dict[str, str]:
    """`{prop: type}` for a node label from ``config/schema_baseline.yaml``."""
    if baseline is None:
        if not SCHEMA_BASELINE_PATH.exists():
            return {}
        baseline = yaml.safe_load(SCHEMA_BASELINE_PATH.read_text(encoding="utf-8"))
    nodes = ((baseline or {}).get("schema") or {}).get("nodes") or {}
    node = nodes.get(label) or {}
    props = node.get("properties") or {}
    if isinstance(props, list):
        return {p: "" for p in props}
    return {str(k): str(v) for k, v in props.items()}


def _vocab_applies_to(key: str, cfg: dict) -> list[str]:
    """Graph identifiers whose ControlledVocabulary nodes belong on this page."""
    out = [cfg["label"], cfg["gene_rel"]]
    if cfg.get("parent_label"):
        out.append(cfg["parent_label"])
    for rel, _target, _kind in cfg.get("bridges_out") or []:
        out.append(rel)
    return out


def load_vocab_values(cfg_by_key: dict) -> dict[str, dict[str, list]] | None:
    """Read ControlledVocabulary values from a live KG, or None when unreachable.

    Returns ``{ontology_key: {"<applies_to>.<property>": [values]}}``. The
    build never requires Neo4j: any failure (no driver, no server, auth) falls
    back silently to ``None`` and the rendered page points at
    ``list_filter_values`` instead.
    """
    try:
        from multiomics_explorer.kg.connection import GraphConnection

        conn = GraphConnection()
        try:
            rows = conn.execute_query(
                "MATCH (v:ControlledVocabulary) "
                "RETURN v.applies_to AS applies_to, v.property AS property, "
                "v.values AS values",
                timeout=10,
            )
        finally:
            conn.close()
    except Exception:
        return None
    by_target: dict[str, dict[str, list]] = {}
    for r in rows:
        if not r.get("values"):
            continue
        by_target.setdefault(r["applies_to"], {})[r["property"]] = list(r["values"])
    out: dict[str, dict[str, list]] = {}
    for key, cfg in cfg_by_key.items():
        merged: dict[str, list] = {}
        for target in _vocab_applies_to(key, cfg):
            for prop, values in (by_target.get(target) or {}).items():
                merged[f"{target}.{prop}"] = values
        out[key] = merged
    return out


def _para(text) -> list[str]:
    """Normalize a yaml scalar/list into markdown paragraph lines."""
    if isinstance(text, list):
        return [f"- {str(t).strip()}" for t in text] + [""]
    return [str(text).strip(), ""]


def render_ontology(key: str, data: dict, vocab_values: dict | None = None) -> str:
    """Render one ``docs://ontologies/{key}`` page.

    ``data`` is the hand-authored yaml (``ONTOLOGY_YAML_KEYS``);
    ``vocab_values`` is ``{"<applies_to>.<prop>" | "<prop>": [values]}`` from a
    live ``ControlledVocabulary`` read, or ``None`` when no KG was reachable
    (the page then points at ``list_filter_values``).
    """
    from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG, ontology_trust_axes

    cfg = ONTOLOGY_CONFIG[key]
    label = cfg["label"]
    parent_label = cfg.get("parent_label")
    hierarchical = bool(cfg.get("hierarchy_rels"))
    axes = ontology_trust_axes(key)
    display = ONTOLOGY_DISPLAY_NAMES.get(key, key)

    L: list[str] = []
    L.append(f"# {display} (`{key}`)")
    L.append("")
    L.append(
        f"Generated from `inputs/ontologies/{key}.yaml`, the `ONTOLOGY_CONFIG` "
        "registry and `config/schema_baseline.yaml` — do not edit. "
        "Index: `docs://ontologies/index`."
    )
    L.append("")

    L.append("## What it is")
    L.append("")
    L += _para(data.get("what_it_is", ""))
    L.append("## How genes get annotated")
    L.append("")
    L += _para(data.get("method", ""))
    L.append("## Identifier form")
    L.append("")
    L += _para(data.get("id_form", ""))
    L.append("## Hierarchy")
    L.append("")
    L += _para(data.get("hierarchy", ""))

    # --- registry row --------------------------------------------------
    L.append("## Graph shape (from the registry)")
    L.append("")
    L.append("| | |")
    L.append("|---|---|")
    labels = f"`{label}`" + (f" (parent label `{parent_label}`)" if parent_label else "")
    L.append(f"| Node label | {labels} |")
    L.append(f"| Gene → term edge | `{cfg['gene_rel']}` |")
    if hierarchical:
        rels = ", ".join(f"`{r}`" for r in cfg["hierarchy_rels"])
        L.append(f"| Hierarchy edges (child → parent) | {rels} |")
    else:
        L.append("| Hierarchy edges | none — flat ontology (`level=0` only, nothing to expand) |")
    if cfg.get("bridge"):
        L.append(
            f"| Reached via | `{cfg['bridge']['node_label']}` terms through "
            f"`{cfg['bridge']['edge']}` (the gene edge belongs to that ontology) |"
        )
    index_cell = f"`{cfg['fulltext_index']}`"
    if cfg.get("parent_fulltext_index"):
        index_cell += f", `{cfg['parent_fulltext_index']}`"
    L.append(f"| Fulltext index | {index_cell} |")
    if cfg.get("facet"):
        f = cfg["facet"]
        L.append(f"| Facet param | `{f['param']}` (node prop `{f['prop']}`) |")
    if axes:
        L.append("| Trust axes on the gene edge | " + ", ".join(f"`{a}`" for a in axes) + " |")
        if cfg.get("trust", {}).get("rank_prop"):
            L.append(f"| Rank prop | `{cfg['trust']['rank_prop']}` |")
    else:
        L.append("| Trust axes on the gene edge | none — native scalars only |")
    if cfg.get("compact_edge"):
        cols = ", ".join(f"`{c}`" for c in cfg["compact_edge"])
        L.append(f"| Compact edge columns | {cols} |")
    if cfg.get("verbose_edge"):
        cols = []
        for entry in cfg["verbose_edge"]:
            if isinstance(entry, str):
                cols.append(f"`{entry}`")
            else:
                prop, col = entry
                cols.append(f"`{col}` (edge prop `{prop}`)")
        L.append(f"| Verbose edge detail | {', '.join(cols)} |")
    if cfg.get("leaf_attachment"):
        la = cfg["leaf_attachment"]
        L.append(
            f"| Leaf mode predicate | `{la['prop']} = '{la['value']}'` "
            f"unless `{la['override_param']}=True` |"
        )
    if cfg.get("term_verbose"):
        cols = ", ".join(f"`{c}`" for c in cfg["term_verbose"])
        L.append(f"| Term columns, verbose `search_ontology` | {cols} |")
    if cfg.get("term_details_compact"):
        cols = ", ".join(f"`{c}`" for c in cfg["term_details_compact"])
        L.append(f"| Extra compact columns, `ontology_term_details` | {cols} |")
    if cfg.get("discusses_rel"):
        L.append(f"| Literature index | `{cfg['discusses_rel']}` (`discussed_by_n_publications`) |")
    bridges = cfg.get("bridges_out") or []
    if bridges:
        rows = "; ".join(
            f"`{rel}` → `{target}` (*{kind}*)" for rel, target, kind in bridges
        )
        L.append(f"| Bridges out (`links_out`) | {rows} |")
    else:
        L.append("| Bridges out (`links_out`) | none |")
    inbound = [
        (okey, rel, kind)
        for okey, ocfg in ONTOLOGY_CONFIG.items()
        for rel, target, kind in (ocfg.get("bridges_out") or [])
        if target == key
    ]
    if inbound:
        rows = "; ".join(f"`{rel}` from `{okey}` (*{kind}*)" for okey, rel, kind in inbound)
        L.append(f"| Bridges in (read from the source term) | {rows} |")
    L.append("")
    L.append(
        "Bridges are forward-only: `ontology_term_details` lists `links_out` on "
        "the source term; there is no `links_in`. `composition` = built from these "
        "parts; `membership` = one of that ontology's known members; `router` = a "
        "computed cross-reference, recall-biased, never a gene-function call."
    )
    L.append("")

    # --- node props ----------------------------------------------------
    L.append(f"## Node properties (`{label}`)")
    L.append("")
    props = _label_props(label)
    if props:
        L.append("| Property | Type | Meaning |")
        L.append("|---|---|---|")
        for prop in sorted(props):
            L.append(f"| `{prop}` | {props[prop] or '—'} | {_NODE_PROP_NOTES.get(prop, '')} |")
        L.append("")
    else:
        L.append("No baseline entry for this label.")
        L.append("")
    if parent_label:
        pprops = _label_props(parent_label)
        if pprops:
            L.append(
                f"Parent label `{parent_label}`: "
                + ", ".join(f"`{p}`" for p in sorted(pprops)) + "."
            )
            L.append("")
    L.append(
        "`ontology_term_details(verbose=True)` returns every property as "
        "`properties`; a compact column that is missing on the node is absent, "
        "not null (`docs://guide/conventions`)."
    )
    L.append("")

    # --- applicable filter types ------------------------------------------
    L.append("## Applicable filter types")
    L.append("")
    filter_types = applicable_filter_types(key)
    if filter_types:
        for ft in filter_types:
            scope = "" if ft in _UNSCOPED_FILTER_TYPES else f', ontology="{key}"'
            L.append(f'- `{ft}` — `list_filter_values(filter_type="{ft}"{scope})`')
        L.append("")
        L.append(
            "Values are read live from the KG's `ControlledVocabulary` nodes at "
            "call time; this page never quotes them. `trust_axes` "
            f"(`list_filter_values(filter_type=\"trust_axes\", ontology=\"{key}\")`) "
            "lists which comparable axes the gene edge carries."
        )
    else:
        L.append(
            "none — the gene edge carries native scalars only (no trust axes, "
            "no ontology-owned categorical, no bridges), so no "
            "`list_filter_values` type is scoped to this ontology. Values on "
            "other tools' filters are still read live from the KG's "
            "`ControlledVocabulary` nodes at call time."
        )
    if vocab_values:
        L.append("")
        L.append("Snapshot of vocabulary values at build time (`--live-vocab`):")
        L.append("")
        for name in sorted(vocab_values):
            L.append(f"- `{name}`: " + ", ".join(f"`{v}`" for v in vocab_values[name]))
    L.append("")

    # --- human sections ----------------------------------------------------
    L.append("## Interpretation")
    L.append("")
    L += _para(data.get("interpretation", ""))
    L.append("## Informativeness rule")
    L.append("")
    L += _para(data.get("informativeness_rule", ""))
    L.append("## Pitfalls")
    L.append("")
    L += _para(data.get("pitfalls", ""))
    L.append("## Typical questions")
    L.append("")
    for q in data.get("typical_questions") or []:
        L.append(f"- {str(q).strip()}")
    L.append("")

    # --- tools -------------------------------------------------------------
    L.append("## Tools")
    L.append("")
    L.append(
        f"- `search_ontology(ontology=['{key}'])` — browse (no `search_text`; "
        "sorted by `gene_count`, filter with `level` / `min_gene_count` / "
        "`organism`) or Lucene search over term names."
    )
    L.append(
        "- `ontology_term_details(term_ids=[...])` — one term or a batch: "
        "parents, children, `links_out` bridges, `gene_count` / "
        "`organism_count`, and per-organism counts with `verbose=True`."
    )
    L.append(
        f"- `genes_by_ontology(ontology='{key}', organism=..., term_ids=[...] | level=N)` "
        "— term → genes (TERM2GENE for enrichment); "
        f"`gene_ontology_terms(ontology=['{key}'], locus_tags=[...])` — genes → terms."
    )
    L.append(
        f"- `ontology_landscape(ontology=['{key}'])` then `pathway_enrichment` / "
        f"`cluster_enrichment(ontology='{key}', level=N)` — ORA."
    )
    L.append("")

    L.append("## See also")
    L.append("")
    for link in data.get("see_also") or []:
        L.append(f"- `{str(link).strip()}`")
    L.append("")
    return "\n".join(L)


_SUMMARY_ABBREVIATIONS = {"e.g", "i.e", "cf", "vs", "etc", "et al", "approx"}


def _summary_sentence(text: str, max_len: int = 110) -> str:
    """First sentence of the first paragraph of `text`, whole words only.

    YAML `|` blocks hard-wrap prose, so the paragraph is re-joined before
    the cut. The sentence ends at the first `. ` outside parentheses that
    is not an abbreviation (`e.g.`, `i.e.`, ...). If that sentence exceeds
    `max_len`, cut at the last word boundary before `max_len` and append
    `…`. The result always ends with `.` or `…` (or is empty).
    """
    paragraph = text.strip().split("\n\n")[0]
    joined = " ".join(line.strip() for line in paragraph.split("\n") if line.strip())
    if not joined:
        return ""
    depth = 0
    end = None
    for i, ch in enumerate(joined):
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif ch == "." and depth == 0 and (i + 1 == len(joined) or joined[i + 1] == " "):
            head = joined[:i]
            last_word = head.rsplit(" ", 1)[-1].lower().lstrip("(`*\"")
            if last_word in _SUMMARY_ABBREVIATIONS or len(last_word) == 1:
                continue
            end = i + 1
            break
    sentence = joined[:end] if end is not None else joined.rstrip()
    if not sentence.endswith("."):
        sentence += "."
    if len(sentence) <= max_len:
        return sentence
    cut = sentence[:max_len].rsplit(" ", 1)[0]
    if cut.count("(") > cut.count(")"):  # never end on an open parenthetical
        cut = cut[:cut.rfind("(")]
    return cut.rstrip(" ,;:—-") + "…"


def render_ontology_index(inputs: dict) -> str:
    """Render ``docs://ontologies/index`` from ``{key: yaml_data}``."""
    from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG, ontology_trust_axes

    L: list[str] = []
    L.append("# Ontology reference index")
    L.append("")
    L.append(
        "One page per supported ontology — what it is, how genes get "
        "annotated, identifier form, hierarchy, the registry row (labels, "
        "edges, trust axes, bridges), node properties, the applicable "
        "`list_filter_values` filter types, interpretation and pitfalls. Open "
        "`docs://ontologies/{key}` for the detail; `key` is the value you "
        "pass as `ontology=` to `search_ontology`, `genes_by_ontology`, "
        "`gene_ontology_terms`, `ontology_landscape` and the enrichment tools. "
        "`ontology_term_details` is cross-ontology and takes self-prefixed "
        "term IDs instead."
    )
    L.append("")
    baseline = None
    if SCHEMA_BASELINE_PATH.exists():
        baseline = yaml.safe_load(SCHEMA_BASELINE_PATH.read_text(encoding="utf-8"))
    L.append(
        "| key | Ontology | Node label | Levels | Hierarchy | Trust | "
        "Trust axes | Bridges out | Summary |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|")
    for key, cfg in ONTOLOGY_CONFIG.items():
        data = inputs.get(key) or {}
        hierarchy = _hierarchy_kind(key, cfg, baseline)
        if cfg.get("facet"):
            hierarchy += f", facet `{cfg['facet']['param']}`"
        trust_axes = ontology_trust_axes(key)
        axes = ", ".join(trust_axes) or "—"
        trust = "yes" if trust_axes else "no"
        bridges = ", ".join(
            f"{target} ({kind})" for _rel, target, kind in (cfg.get("bridges_out") or [])
        ) or "—"
        summary = _summary_sentence(str(data.get("what_it_is", "")))
        summary = summary.replace("|", "\\|")
        L.append(
            f"| `{key}` | {ONTOLOGY_DISPLAY_NAMES.get(key, key)} | `{cfg['label']}` | "
            f"{_level_range_cell(key)} | {hierarchy} | {trust} | {axes} | {bridges} | {summary} |"
        )
    L.append("")
    L.append(
        "`Levels` is the observed `level` range (0 = root / broadest); "
        "`Hierarchy` is tree, DAG (GO — `level` is a min-path proxy) or flat; "
        "`Trust` says whether the gene edge carries comparable trust axes "
        "(`evidence` / `sources`, filterable on `genes_by_ontology` and friends)."
    )
    L.append("")
    L.append(
        "Cross-cutting semantics live in `docs://analysis/annotation_evidence` "
        "(trust ladder, rank-vs-filter, bridges) and `docs://guide/conventions` "
        "(`level` convention, browse vs search, lockstep paging, strip rule)."
    )
    L.append("")
    return "\n".join(L)


def build_ontologies(*, live_vocab: bool = False) -> int:
    """Render every ``inputs/ontologies/*.yaml`` into ``references/ontologies/``.

    Returns the number of pages written (17 + index on a complete input set).
    """
    from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG

    inputs: dict[str, dict] = {}
    for key in ONTOLOGY_CONFIG:
        path = ONTOLOGY_INPUTS_DIR / f"{key}.yaml"
        if not path.exists():
            print(f"  SKIP ontology {key}: no {path.name}")
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        missing = [k for k in ONTOLOGY_YAML_KEYS if not data.get(k)]
        if missing:
            print(f"  WARN ontology {key}: empty fields {missing}")
        inputs[key] = data
    if not inputs:
        return 0

    # Deterministic by default: pages point at `list_filter_values` (values
    # are live there and the explorer's vocabulary-hash pin already flags
    # stale baked lists). `--live-vocab` opts in to embedding a snapshot.
    vocab = None
    if live_vocab:
        vocab = load_vocab_values({k: ONTOLOGY_CONFIG[k] for k in inputs})
        if vocab is None:
            print("  (no KG reachable — vocabulary values point at list_filter_values)")
        for line in check_level_ranges_live():
            print(f"  WARN level range drift — update ONTOLOGY_LEVEL_RANGES: {line}")

    ONTOLOGY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for key, data in inputs.items():
        md = render_ontology(key, data, vocab_values=(vocab or {}).get(key))
        out = ONTOLOGY_OUTPUT_DIR / f"{key}.md"
        out.write_text(md, encoding="utf-8")
        print(f"  OK   ontology {key}: {out.relative_to(Path.cwd())}")
        written += 1
    index = ONTOLOGY_OUTPUT_DIR / "index.md"
    index.write_text(render_ontology_index(inputs), encoding="utf-8")
    print(f"  OK   ontology index: {index.relative_to(Path.cwd())}")
    return written + 1


# --- docs://index (llm-review 2b.4 D1) ---

# Hard char cap on the rendered index (llm-review 2b.4 controller ruling
# supersedes the original 3,200-char/800-tok figure in the task brief,
# which is arithmetically impossible against the current corpus — 42 brief
# + 42 full tool pages + 17 ontologies alone are ~100 rows). Enforced by
# shortening the read-when text on guide/analysis/examples/ontology-index
# rows (the only rows that carry one) — rows are never dropped.
INDEX_MAX_CHARS = 6000

_READ_WHEN_HEADING_PREFIXES = ("#",)
_READ_WHEN_SKIP_PREFIXES = ("|", "-", "`", "<", "(", "*", "import ", "from ", "#!")


def _read_when(path: Path, max_len: int = 110) -> str:
    """First sentence of `path`'s first prose paragraph, cut to `max_len`.

    Skips markdown headings, list/table/code/html lines and Python
    docstring/import boilerplate while looking for the first prose line,
    then collects the contiguous non-indented lines that follow it (the
    rest of that paragraph) before handing the joined text to
    `_summary_sentence` for the sentence cut.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    paragraph: list[str] = []
    for line in lines:
        raw = line.strip()
        if raw.startswith(('"""', "'''")):
            raw = raw[3:].strip()
        if not raw:
            if paragraph:
                break
            continue
        if raw.startswith(_READ_WHEN_HEADING_PREFIXES) or raw.startswith(_READ_WHEN_SKIP_PREFIXES):
            if paragraph:
                break
            continue
        if paragraph and line != line.lstrip():
            break  # indented continuation (e.g. a list) — new block, stop
        paragraph.append(raw)
    if not paragraph:
        return path.stem
    return _summary_sentence(" ".join(paragraph), max_len=max_len)


def _index_tok(path: Path) -> int:
    return len(path.read_bytes()) // 4


def _render_docs_index_at(read_when_max_len: int) -> str:
    """Render `docs://index` with read-when text cut to `read_when_max_len`."""
    refs = OUTPUT_DIR.parent  # .../references
    examples_dir = Path(__file__).resolve().parent.parent / "examples"

    L: list[str] = ["# docs://index — every page, its size, when to read it", ""]

    L += ["## Guides", ""]
    for f in sorted((refs / "guide").glob("*.md")):
        uri = f"docs://guide/{f.stem}"
        L.append(f"- `{uri}` — ~{_index_tok(f)} tok — {_read_when(f, read_when_max_len)}")
    L.append("")

    L += ["## Tools (brief)", ""]
    for f in sorted(OUTPUT_DIR.glob("*.md")):
        uri = f"docs://tools/{f.stem}"
        L.append(f"- `{uri}` — ~{_index_tok(f)} tok")
    L.append("")

    L += [
        "## Tool full pages",
        "",
        "Append /full for the complete page — all worked examples + full "
        "response format.",
        "",
    ]
    for f in sorted(FULL_OUTPUT_DIR.glob("*.md")):
        uri = f"docs://tools/{f.stem}/full"
        L.append(f"- `{uri}` — ~{_index_tok(f)} tok")
    L.append("")

    L += ["## Analysis", ""]
    for f in sorted((refs / "analysis").glob("*.md")):
        uri = f"docs://analysis/{f.stem}"
        L.append(f"- `{uri}` — ~{_index_tok(f)} tok — {_read_when(f, read_when_max_len)}")
    L.append("")

    # Ontology pages are compact like tool pages (docs://ontologies/index
    # already gives orientation); docs://ontologies/index itself gets a
    # read-when row like a guide.
    L += ["## Ontologies", ""]
    for f in sorted((refs / "ontologies").glob("*.md")):
        uri = f"docs://ontologies/{f.stem}"
        if f.stem == "index":
            L.append(f"- `{uri}` — ~{_index_tok(f)} tok — {_read_when(f, read_when_max_len)}")
        else:
            L.append(f"- `{uri}` — ~{_index_tok(f)} tok")
    L.append("")

    L += ["## Examples", ""]
    for f in sorted(examples_dir.glob("*.py")):
        uri = f"docs://examples/{f.name}"
        L.append(f"- `{uri}` — ~{_index_tok(f)} tok — {_read_when(f, read_when_max_len)}")
    L.append("")

    return "\n".join(L) + "\n"


def render_docs_index() -> str:
    """Render `docs://index`, binary-searching the read-when cut length so the
    whole page stays within `INDEX_MAX_CHARS` without ever dropping a row.
    """
    lo, hi = 0, 110
    if len(_render_docs_index_at(hi)) <= INDEX_MAX_CHARS:
        return _render_docs_index_at(hi)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(_render_docs_index_at(mid)) <= INDEX_MAX_CHARS:
            lo = mid
        else:
            hi = mid - 1
    return _render_docs_index_at(lo)


def lint_index_fresh() -> list[str]:
    """Flag `references/index.md` if it disagrees with a fresh re-render."""
    index_path = OUTPUT_DIR.parent / "index.md"
    current = render_docs_index()
    if not index_path.exists() or index_path.read_text(encoding="utf-8") != current:
        return ["index stale — rerun build"]
    return []


def main():
    parser = argparse.ArgumentParser(description="Build about-content for MCP tools")
    parser.add_argument("tools", nargs="*", help="Tool names to build (default: all with input files)")
    parser.add_argument("--skeleton", metavar="TOOL", help="Generate input YAML skeleton for a tool")
    parser.add_argument("--all", action="store_true", help="Build for all registered tools")
    parser.add_argument(
        "--ontologies",
        action="store_true",
        help="Build only the per-ontology reference (references/ontologies/*.md)",
    )
    parser.add_argument(
        "--live-vocab",
        action="store_true",
        help="Embed a ControlledVocabulary snapshot from a reachable KG into the "
             "ontology pages (default: pages point at list_filter_values)",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help=(
            "Scan rendered md for outfacing-doc style-rule violations, plus "
            "the inputs/tools/*.yaml example-entry checks (unknown keys, "
            "response block naming no envelope key). "
            "With positional tool names, scopes to those tools' md. "
            "Exit 1 if any violation, 0 if clean."
        ),
    )
    args = parser.parse_args()

    if args.lint:
        if args.tools:
            paths: list[Path] = []
            for name in args.tools:
                p = Path(name)
                if p.exists():
                    paths.append(p)
                else:
                    md_path = OUTPUT_DIR / f"{name}.md"
                    if not md_path.exists():
                        print(
                            f"Error: '{name}' is neither a file nor a registered tool md",
                            file=sys.stderr,
                        )
                        sys.exit(2)
                    paths.append(md_path)
                    full_md_path = FULL_OUTPUT_DIR / f"{name}.md"
                    if full_md_path.exists():
                        paths.append(full_md_path)
        else:
            repo_root = Path(__file__).resolve().parent.parent
            skills_refs = (
                repo_root
                / "multiomics_explorer"
                / "skills"
                / "multiomics-kg-guide"
                / "references"
            )
            paths = (
                sorted(OUTPUT_DIR.glob("*.md"))
                + sorted(FULL_OUTPUT_DIR.glob("*.md"))
                + sorted((skills_refs / "guide").glob("*.md"))
                + sorted((skills_refs / "analysis").glob("*.md"))
                + sorted((skills_refs / "ontologies").glob("*.md"))
                + [repo_root / "multiomics_explorer" / "api" / "functions.py"]
                + sorted((repo_root / "multiomics_explorer" / "analysis").glob("*.py"))
                + sorted((repo_root / "examples").glob("*.py"))
                + [repo_root / "examples" / "README.md"]
            )
            paths = [p for p in paths if p.exists()]
            if not paths:
                print("Error: no scannable files found", file=sys.stderr)
                sys.exit(2)
        rc = run_lint(paths)
        if not args.tools:
            # Example-entry lints over inputs/tools/*.yaml: unknown keys and
            # response blocks that name no envelope key of the tool's model.
            schemas = get_tool_schemas()
            yaml_violations = lint_example_yaml(schemas)
            for v in yaml_violations:
                print(v, file=sys.stderr)
            if yaml_violations:
                rc = rc or 1
            # Five-slot tool descriptions stay within the description budget.
            desc_violations = lint_description_length(schemas)
            for v in desc_violations:
                print(v, file=sys.stderr)
            if desc_violations:
                rc = rc or 1
            # Brief pages stay under BRIEF_MAX_CHARS.
            brief_violations = lint_brief_size(sorted(OUTPUT_DIR.glob("*.md")))
            for v in brief_violations:
                print(v, file=sys.stderr)
            if brief_violations:
                rc = rc or 1
            # docs://index matches a fresh re-render.
            index_violations = lint_index_fresh()
            for v in index_violations:
                print(v, file=sys.stderr)
            if index_violations:
                rc = rc or 1
        sys.exit(rc)

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
        out_path.write_text(skeleton, encoding="utf-8")
        print(f"Generated skeleton: {out_path.relative_to(Path.cwd())}")
        return

    if args.ontologies:
        print("Building per-ontology reference:")
        n = build_ontologies(live_vocab=args.live_vocab)
        print(f"\nDone: {n} ontology pages built")
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

    if args.all or not args.tools:
        print("\nBuilding per-ontology reference:")
        n = build_ontologies(live_vocab=args.live_vocab)
        print(f"Done: {n} ontology pages built")

        print("\nBuilding docs index:")
        index_text = render_docs_index()
        index_path = OUTPUT_DIR.parent / "index.md"
        index_path.write_text(index_text, encoding="utf-8")
        print(f"  OK   docs index: {index_path.relative_to(Path.cwd())} ({len(index_text)} chars)")


if __name__ == "__main__":
    main()
