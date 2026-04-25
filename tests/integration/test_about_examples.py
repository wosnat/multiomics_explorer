"""Integration tests: verify about-content examples execute against live KG.

Parses example-call blocks from about markdown files, executes them via
the API layer, and verifies responses match expected-keys.
"""

import inspect
import re
from pathlib import Path

import pytest

import multiomics_explorer.api.functions as api

ABOUT_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "multiomics_explorer" / "skills" / "multiomics-kg-guide" / "references" / "tools"
)


def _parse_tool_expected_keys(content: str) -> list[str] | None:
    """Extract the first expected-keys block from the Response format section."""
    match = re.search(r"```expected-keys\n(.+?)\n```", content, re.DOTALL)
    if match:
        return [k.strip() for k in match.group(1).split(",")]
    return None


def _extract_top_level_keys(json_text: str) -> list[str]:
    """Extract top-level keys from a JSON-like response (handles single-line
    and multi-line, and tolerates '...' placeholders)."""
    keys = []
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(json_text):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"' and not in_string:
            in_string = True
            continue
        if ch == '"' and in_string:
            in_string = False
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            depth += 1
        elif ch in ('}', ']'):
            depth -= 1
        elif ch == ':' and depth == 1:
            # Find the key before this colon — scan back for "key"
            before = json_text[:i].rstrip()
            m = re.search(r'"(\w+)"\s*$', before)
            if m:
                keys.append(m.group(1))
    return keys


def _parse_examples(content: str) -> list[dict]:
    """Extract example-call and example-response blocks from about content.

    Returns list of {"call": str, "response_keys": list[str] | None}.
    """
    # Get tool-level expected-keys (from Response format section)
    tool_keys = _parse_tool_expected_keys(content)

    examples = []
    # Split into sections by ```example-call
    parts = content.split("```example-call")
    for part in parts[1:]:  # skip before first example-call
        call_end = part.index("```")
        call = part[:call_end].strip()

        # Look for example-response after this call
        remainder = part[call_end + 3:]
        response_keys = None
        resp_match = re.search(r"```example-response\n(.+?)\n```", remainder, re.DOTALL)
        if resp_match:
            response_keys = _extract_top_level_keys(resp_match.group(1))

        examples.append({
            "call": call,
            "tool_expected_keys": tool_keys,
            "response_keys": response_keys,
        })
    return examples


def _execute_call(call_str: str, conn) -> object:
    """Execute an example-call string via the API layer.

    Parses "tool_name(param1='val1', param2='val2')" and calls
    api.tool_name(param1='val1', param2='val2', conn=conn).
    """
    match = re.match(r"(\w+)\((.*)\)$", call_str, re.DOTALL)
    if not match:
        pytest.fail(f"Cannot parse example-call: {call_str}")

    func_name = match.group(1)
    args_str = match.group(2).strip()

    func = getattr(api, func_name, None)
    if func is None:
        pytest.skip(f"API function '{func_name}' not found (tool may not have API equivalent)")

    # Parse kwargs from the call string
    kwargs = {}
    if args_str:
        # Use a safe eval approach — only allow simple literals
        # Build a dict from "key=value, key=value" pairs
        for part in _split_kwargs(args_str):
            key, _, value = part.partition("=")
            key = key.strip()
            value = value.strip()
            # Evaluate simple Python literals
            kwargs[key] = eval(value)  # noqa: S307 — controlled input from our own files

    # About-content examples document the MCP-shape, but we call the API layer
    # directly. Route MCP-wrapper-only kwargs (anything not in the API signature)
    # through to_envelope() instead, so EnrichmentResult-returning tools render
    # the user-visible envelope.
    api_params = set(inspect.signature(func).parameters)
    envelope_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k not in api_params}

    kwargs["conn"] = conn
    result = func(**kwargs)
    if hasattr(result, "to_envelope"):
        result = result.to_envelope(**envelope_kwargs)
    return result


def _split_kwargs(args_str: str) -> list[str]:
    """Split 'key=val, key=val' respecting strings and nested structures."""
    parts = []
    depth = 0
    current = []
    in_string = False
    string_char = None

    for char in args_str:
        if in_string:
            current.append(char)
            if char == string_char:
                in_string = False
        elif char in ('"', "'"):
            in_string = True
            string_char = char
            current.append(char)
        elif char in ("(", "[", "{"):
            depth += 1
            current.append(char)
        elif char in (")", "]", "}"):
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append("".join(current))
    return parts


def _collect_test_cases() -> list[tuple[str, dict]]:
    """Collect all (tool_name, example) pairs from about files."""
    cases = []
    if not ABOUT_DIR.exists():
        return cases
    for path in sorted(ABOUT_DIR.glob("*.md")):
        content = path.read_text()
        examples = _parse_examples(content)
        for ex in examples:
            cases.append((path.stem, ex))
    return cases


_CASES = _collect_test_cases()
_CASE_IDS = [f"{name}:{ex['call'][:40]}" for name, ex in _CASES]


@pytest.mark.kg
@pytest.mark.parametrize("tool_name,example", _CASES, ids=_CASE_IDS)
def test_example_executes(conn, tool_name, example):
    """Example-call executes without error against live KG."""
    result = _execute_call(example["call"], conn)
    assert result is not None


@pytest.mark.kg
@pytest.mark.parametrize("tool_name,example", _CASES, ids=_CASE_IDS)
def test_example_has_expected_keys(conn, tool_name, example):
    """Response contains all expected-keys from the about file (API-level keys)."""
    if not example["tool_expected_keys"]:
        pytest.skip("No expected-keys block in about file")

    result = _execute_call(example["call"], conn)

    if isinstance(result, dict):
        actual_keys = set(result.keys())
    else:
        actual_keys = set(result.__dict__.keys()) if hasattr(result, "__dict__") else set()

    # 'returned' and 'truncated' are added by MCP wrapper, not API
    mcp_only_keys = {"returned", "truncated"}
    for key in example["tool_expected_keys"]:
        if key in mcp_only_keys:
            continue
        assert key in actual_keys, (
            f"Expected key '{key}' not in API response. "
            f"Got: {sorted(actual_keys)}"
        )


@pytest.mark.kg
@pytest.mark.parametrize("tool_name,example", _CASES, ids=_CASE_IDS)
def test_example_response_keys_match(conn, tool_name, example):
    """Top-level keys in example-response match actual response."""
    if not example["response_keys"]:
        pytest.skip("No example-response block for this example")

    result = _execute_call(example["call"], conn)

    if isinstance(result, dict):
        actual_keys = set(result.keys())
    else:
        actual_keys = set()

    # 'returned' and 'truncated' are added by MCP wrapper, not API
    mcp_only_keys = {"returned", "truncated"}
    for key in example["response_keys"]:
        if key in mcp_only_keys:
            continue
        assert key in actual_keys, (
            f"example-response shows key '{key}' but actual response "
            f"doesn't have it. Got: {sorted(actual_keys)}"
        )
