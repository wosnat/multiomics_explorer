#!/usr/bin/env python3
"""Build about-content markdown for MCP tools.

Merges auto-extracted Pydantic schema data with human-authored input
YAML files to produce per-tool about pages served via MCP resource.

Output: writes directly to
``multiomics_explorer/skills/multiomics-kg-guide/references/tools/{tool}.md``
(no separate sync step — that path is served).

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
| ``examples``              | list[{title, call, response, steps}] | "Few-shot examples" section                       |
| ``verbose_fields``        | list[str]                     | Splits per-result table into compact + verbose          |
| ``chaining``              | list[str]                     | "Chaining patterns" section                             |
| ``mistakes``              | list (str or {wrong, right})  | "Good to know" / "Common mistakes" sections             |
| ``response_notes``        | list[{title, body}]           | Subsections under "Response format"                     |
| ``python_returns``        | str (class name)              | Replaces "returns dict with keys" with object-shape hint|
| ``python_returns_example``| str (URI)                     | Appends a `See <uri>` line (only when python_returns set)|

Auto-generated sections (params table, response format, envelope keys) are
extracted from Pydantic models in ``mcp_server/tools.py``.
"""

import argparse
import asyncio
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
CONDITIONAL_ENVELOPE_KEYS = {"evidence_score_signals"}


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
    has_results = bool(result_fields) or "results" in schema.get("output_schema", {}).get("properties", {})
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
    lines.extend(_build_package_import_section(
        tool_name=tool_name,
        params=params,
        envelope=envelope,
        has_results=has_results,
        python_returns=(input_data or {}).get("python_returns"),
        python_returns_example=(input_data or {}).get("python_returns_example"),
    ))

    return "\n".join(lines)


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
        # API returns a subset of the MCP envelope (no returned/truncated wrapper)
        api_keys = [
            f["name"] for f in envelope
            if f["name"] not in ("returned", "truncated")
        ]
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
    output_path = OUTPUT_DIR / f"{tool_name}.md"

    input_data = None
    if input_path.exists():
        input_data = yaml.safe_load(input_path.read_text(encoding="utf-8"))

    markdown = render_about(tool_name, schema, input_data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    status = "built" if input_data else "built (no input YAML — TODOs remain)"
    print(f"  OK   {tool_name}: {output_path.relative_to(Path.cwd())} [{status}]")
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
    "level_kind": "what a level means in this ontology (see the vocabulary below)",
    "level_is_best_effort": "sparse `'true'` flag — DAG term whose depth is a min-path proxy",
    "gene_count": "genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones",
    "direct_gene_count": "genes attached to this exact node (not descendants); absent where it would be vacuous",
    "organism_count": "organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is)",
    "member_count": "upstream family size (source-database members), not KG genes",
}


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

    # --- vocab -----------------------------------------------------------
    L.append("## Controlled vocabularies")
    L.append("")
    if vocab_values:
        for name in sorted(vocab_values):
            values = vocab_values[name]
            L.append(f"- `{name}`: " + ", ".join(f"`{v}`" for v in values))
        L.append("")
        L.append(
            "Values are read from the KG's `ControlledVocabulary` nodes at build "
            f"time; confirm live via `list_filter_values(filter_type=..., ontology='{key}')`."
        )
    else:
        L.append(
            "Values: see `list_filter_values(filter_type=..., ontology="
            f"'{key}')` — `trust_axes`, `evidence`, `sources`, and the "
            "ontology-specific categorical filter types are read from the "
            "KG's `ControlledVocabulary` nodes at call time."
        )
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


def render_ontology_index(inputs: dict) -> str:
    """Render ``docs://ontologies/index`` from ``{key: yaml_data}``."""
    from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG, ontology_trust_axes

    L: list[str] = []
    L.append("# Ontology reference index")
    L.append("")
    L.append(
        "One page per supported ontology — what it is, how genes get "
        "annotated, identifier form, hierarchy, the registry row (labels, "
        "edges, trust axes, bridges), node properties, controlled "
        "vocabularies, interpretation and pitfalls. Open "
        "`docs://ontologies/{key}` for the detail; `key` is the value you "
        "pass as `ontology=` to `search_ontology`, `genes_by_ontology`, "
        "`gene_ontology_terms`, `ontology_landscape` and the enrichment tools. "
        "`ontology_term_details` is cross-ontology and takes self-prefixed "
        "term IDs instead."
    )
    L.append("")
    L.append("| key | Ontology | Node label | Shape | Trust axes | Bridges out | Summary |")
    L.append("|---|---|---|---|---|---|---|")
    for key, cfg in ONTOLOGY_CONFIG.items():
        data = inputs.get(key) or {}
        shape = "hierarchical" if cfg.get("hierarchy_rels") else "flat"
        if cfg.get("facet"):
            shape += f", facet `{cfg['facet']['param']}`"
        axes = ", ".join(ontology_trust_axes(key)) or "—"
        bridges = ", ".join(
            f"{target} ({kind})" for _rel, target, kind in (cfg.get("bridges_out") or [])
        ) or "—"
        summary = str(data.get("what_it_is", "")).strip().split("\n")[0]
        summary = summary.split(". ")[0].rstrip(".")
        summary = summary.replace("|", "\\|")
        L.append(
            f"| `{key}` | {ONTOLOGY_DISPLAY_NAMES.get(key, key)} | `{cfg['label']}` | "
            f"{shape} | {axes} | {bridges} | {summary} |"
        )
    L.append("")
    L.append(
        "Cross-cutting semantics live in `docs://analysis/annotation_evidence` "
        "(trust ladder, rank-vs-filter, bridges) and `docs://guide/conventions` "
        "(`level` convention, browse vs search, lockstep paging, strip rule)."
    )
    L.append("")
    return "\n".join(L)


def build_ontologies() -> int:
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

    vocab = load_vocab_values({k: ONTOLOGY_CONFIG[k] for k in inputs})
    if vocab is None:
        print("  (no KG reachable — vocabulary values point at list_filter_values)")

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
        "--lint",
        action="store_true",
        help=(
            "Scan rendered md for outfacing-doc style-rule violations. "
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
        sys.exit(run_lint(paths))

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
        n = build_ontologies()
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
        n = build_ontologies()
        print(f"Done: {n} ontology pages built")


if __name__ == "__main__":
    main()
