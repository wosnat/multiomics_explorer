#!/usr/bin/env python3
"""Check (or rewrite) the hand-authored ``response:`` blocks in
``multiomics_explorer/inputs/tools/{tool}.yaml`` against the live KG.

The about-content examples show a *response* next to each *call*. Those
blocks were historically hand-typed and drift silently as the KG is rebuilt.
This script executes every ``call`` through the in-memory FastMCP client (so
the result is exactly what an MCP caller sees — MCP-side defaults such as
``limit``, ``SparseRow`` stripping, ``returned`` / ``truncated``) and either

* ``--check`` (default): parses the shown block leniently and compares every
  scalar leaf it contains with the live value at the same path, reporting
  per example ``ok`` / ``drift`` / ``error`` / ``empty`` / ``unparseable`` /
  ``skipped``; exits 1 when any drift / error / empty / unparseable exists.
* ``--write``: rewrites the ``response:`` block from the live result with a
  deterministic trim (see :func:`trim_response` / :class:`TrimConfig`: ≤ 3
  result rows, ≤ 3 entries per other list, ≤ 6 entries per dict-valued
  envelope field, null-heavy rows' nulls folded into one ``"..."`` entry),
  touching nothing else in the YAML (text-level replacement of the block
  only). Caps are overridable (``--max-rows`` etc.). Rerunnable: an
  unchanged KG rewrites identical text.

Skipped examples: those carrying ``illustrative: true``, narratives (``steps:``)
and examples without a ``call:``. In ``--check`` mode examples without a
``response:`` are also skipped (nothing to compare); in ``--write`` mode they
are left untouched too — the block is only rewritten, never added.

Usage::

    uv run python scripts/refresh_examples.py --check
    uv run python scripts/refresh_examples.py --check --tool resolve_gene
    uv run python scripts/refresh_examples.py --write resolve_gene gene_overview
    uv run python scripts/refresh_examples.py --write            # every tool

The parsing / comparison / formatting helpers are pure (no KG) and are unit
tested in ``tests/unit/test_refresh_examples.py``; the live comparison is
exercised per example by ``tests/integration/test_about_examples.py``.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import logging
import math
import re
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUTS_DIR = REPO_ROOT / "multiomics_explorer" / "inputs" / "tools"

ELLIPSIS = "..."
MAX_ROLLUP_ITEMS = 3
MAX_RESULT_ROWS = 3
MAX_DICT_KEYS = 6
MIN_NULLS_TO_ELIDE = 3
MAX_WIDE_ITEMS = 1
WIDE_ENTRY_KEYS = 8
MIN_EMPTY_TO_ELIDE = 3
MAX_STRING_LEN = 100
MAX_NAMED_ELISIONS = 4
RESPONSE_INDENT = "      "  # 6 spaces: `  - title:` (2) + key (4) + block body

STATUS_OK = "ok"
STATUS_DRIFT = "drift"
STATUS_ERROR = "error"
STATUS_EMPTY = "empty"
STATUS_UNPARSEABLE = "unparseable"
STATUS_SKIPPED = "skipped"
FAILING_STATUSES = (STATUS_DRIFT, STATUS_ERROR, STATUS_EMPTY, STATUS_UNPARSEABLE)


# ---------------------------------------------------------------------------
# YAML example discovery
# ---------------------------------------------------------------------------

@dataclass
class Example:
    tool: str
    index: int  # position in the YAML `examples:` list
    title: str
    call: str | None
    response: str | None
    illustrative: bool = False
    has_steps: bool = False
    path: Path | None = None
    # Envelope keys the note is about: never dict-capped or empty-folded.
    keep: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return f"{self.tool}[{self.index}] {self.title}"

    @property
    def skip_reason(self) -> str | None:
        if self.illustrative:
            return "illustrative"
        if self.has_steps:
            return "steps narrative"
        if not self.call:
            return "no call"
        if self.response is None:
            return "no response block"
        return None


def load_examples(path: Path) -> list[Example]:
    """Read every entry of ``examples:`` in one tool YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[Example] = []
    for i, ex in enumerate(data.get("examples") or []):
        if not isinstance(ex, dict):
            continue
        call = ex.get("call")
        out.append(Example(
            tool=path.stem,
            index=i,
            title=str(ex.get("title", "")),
            call=call.strip() if isinstance(call, str) else None,
            response=ex.get("response") if isinstance(ex.get("response"), str) else None,
            illustrative=bool(ex.get("illustrative", False)),
            has_steps="steps" in ex,
            path=path,
            keep=tuple(str(k) for k in (ex.get("keep") or [])),
        ))
    return out


def iter_tool_yamls(tools: list[str] | None = None) -> list[Path]:
    paths = sorted(INPUTS_DIR.glob("*.yaml"))
    if tools:
        wanted = set(tools)
        paths = [p for p in paths if p.stem in wanted]
        missing = wanted - {p.stem for p in paths}
        if missing:
            raise SystemExit(f"No YAML for tool(s): {sorted(missing)}")
    return paths


# ---------------------------------------------------------------------------
# Call-string parsing
# ---------------------------------------------------------------------------

def strip_hash_comments(text: str) -> str:
    """Remove ``# ...`` comments that sit outside string literals."""
    out: list[str] = []
    in_string = False
    quote = ""
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
        elif ch in ('"', "'"):
            in_string = True
            quote = ch
            out.append(ch)
        elif ch == "#":
            # drop to end of line (keep the newline)
            nl = text.find("\n", i)
            if nl == -1:
                break
            i = nl
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def split_kwargs(args_str: str) -> list[str]:
    """Split ``'key=val, key=val'`` respecting strings and nested structures."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    string_char = ""
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
    if "".join(current).strip():
        parts.append("".join(current))
    return parts


def parse_call(call_str: str) -> tuple[str, dict[str, Any]]:
    """``tool(a=1, b=[..])`` → ``("tool", {"a": 1, "b": [...]})``.

    Multi-line calls with trailing ``# comments`` are supported. Values are
    Python literals (``ast.literal_eval`` — strings, numbers, bools, None,
    lists, dicts, tuples); nothing is executed.
    """
    cleaned = strip_hash_comments(call_str).strip()
    match = re.match(r"(\w+)\s*\((.*)\)\s*$", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"Cannot parse call: {call_str!r}")
    name = match.group(1)
    kwargs: dict[str, Any] = {}
    for part in split_kwargs(match.group(2).strip()):
        key, sep, value = part.partition("=")
        if not sep:
            raise ValueError(f"Positional argument not supported in call: {part.strip()!r}")
        try:
            kwargs[key.strip()] = ast.literal_eval(value.strip())
        except (ValueError, SyntaxError) as e:
            raise ValueError(f"Bad literal for {key.strip()!r}: {value.strip()!r} ({e})") from e
    return name, kwargs


# ---------------------------------------------------------------------------
# Shown-response parsing (lenient)
# ---------------------------------------------------------------------------

_ELLIPSIS_KEY_RE = re.compile(r'"\.\.\."\s*:\s*"[^"]*"')         # "...": "<elision note>"
_ELLIPSIS_ITEM_RE = re.compile(r'(?<![\w"])\.\.\.(?![\w"])')      # bare ...
_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")
_DOUBLE_COMMA_RE = re.compile(r",(\s*,)+")
_LEADING_COMMA_RE = re.compile(r"([\[{]\s*),")


def _outside_strings(text: str, fn) -> str:
    """Apply ``fn`` to the stretches of ``text`` outside double-quoted strings
    (a live quote may legitimately contain " ... ")."""
    out, buf, in_str, esc = [], [], False, False
    for ch in text:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                out.append(fn("".join(buf)))
                buf = []
                out.append(ch)
                in_str = True
            else:
                buf.append(ch)
    out.append(fn("".join(buf)))
    return "".join(out)


def _strip_ellipses(text: str) -> str:
    text = _ELLIPSIS_KEY_RE.sub("", text)
    text = _outside_strings(text, lambda seg: _ELLIPSIS_ITEM_RE.sub("", seg))
    # `"...",` and `, "..."` as quoted list items
    text = re.sub(r'"\.\.\."', "", text)
    # collapse the commas left behind
    for _ in range(3):
        text = _DOUBLE_COMMA_RE.sub(",", text)
        text = _LEADING_COMMA_RE.sub(r"\1", text)
        text = _TRAILING_COMMA_RE.sub(r"\1", text)
    return text


def parse_shown_response(text: str) -> Any | None:
    """Parse a hand-authored response block into Python data, or ``None``.

    Lenient: ``#`` comments (outside strings) are removed, ``...`` ellipses
    (bare, quoted, or ``"...": "..."``) are dropped and the commas they leave
    behind are collapsed. Tries JSON5 first (unquoted keys, trailing commas),
    then YAML for the ``key: value`` flow style some blocks use.
    """
    cleaned = textwrap.dedent(_strip_ellipses(strip_hash_comments(text))).strip()
    if not cleaned:
        return None
    try:
        import json5  # optional dependency — present in the dev env
        return json5.loads(cleaned)
    except Exception:
        pass
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    try:
        data = yaml.safe_load(cleaned)
    except Exception:
        return None
    return data if isinstance(data, (dict, list)) else None


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

@dataclass
class Diff:
    path: str
    shown: Any
    live: Any

    def __str__(self) -> str:
        return f"{self.path}: shown={_short(self.shown)} live={_short(self.live)}"


def _short(v: Any, n: int = 80) -> str:
    s = json.dumps(v, default=str, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 3] + "..."


def _is_prose_placeholder(shown: Any, live: Any) -> bool:
    """Shown value is narrative text standing in for a structure."""
    if isinstance(shown, str) and isinstance(live, (list, dict)):
        return True
    if isinstance(shown, list) and isinstance(live, list) and shown and all(
        isinstance(s, str) for s in shown
    ) and live and all(isinstance(x, dict) for x in live):
        return True
    return False


def _scalars_equal(shown: Any, live: Any) -> bool:
    if isinstance(shown, bool) or isinstance(live, bool):
        return shown is live or (
            isinstance(shown, str) and shown.lower() == str(live).lower()
        )
    if isinstance(shown, (int, float)) and isinstance(live, (int, float)):
        if isinstance(shown, float) or isinstance(live, float):
            # tolerate the rounding the shown value applied
            decimals = _decimals(shown)
            return math.isclose(shown, round(live, decimals), rel_tol=1e-9, abs_tol=0.5 * 10 ** -decimals + 1e-12)
        return shown == live
    if isinstance(shown, str) and isinstance(live, str):
        if shown == live:
            return True
        # elided string: "abc..." vs full live string
        if shown.endswith(ELLIPSIS) and live.startswith(shown[: -len(ELLIPSIS)]):
            return True
        return False
    return shown == live


def _decimals(x: float | int) -> int:
    if isinstance(x, int):
        return 0
    s = repr(x)
    if "e" in s or "E" in s:
        return 12
    return len(s.split(".")[1]) if "." in s else 0


def compare(shown: Any, live: Any, path: str = "$") -> list[Diff]:
    """Every scalar leaf present in ``shown`` must equal ``live`` at the same
    path. Lists compare index-wise for the items shown (ellipses were
    stripped, so a shorter shown list is fine). Extra live keys are ignored.
    """
    diffs: list[Diff] = []
    if _is_prose_placeholder(shown, live):
        return diffs
    if isinstance(shown, dict):
        if not isinstance(live, dict):
            return [Diff(path, shown, live)]
        for k, v in shown.items():
            if k == ELLIPSIS:
                continue
            key = str(k)
            if key not in live and isinstance(k, bool):
                key = str(k).lower()
            if key not in live:
                diffs.append(Diff(f"{path}.{key}", v, "<missing>"))
                continue
            diffs.extend(compare(v, live[key], f"{path}.{key}"))
        return diffs
    if isinstance(shown, list):
        if not isinstance(live, list):
            return [Diff(path, shown, live)]
        # Lists of plain strings (warnings, id lists) carry no stable order
        # guarantee — compare as multisets.
        if shown and all(isinstance(v, str) for v in shown) and all(
            isinstance(v, str) for v in live
        ):
            shown_items = [v for v in shown if v != ELLIPSIS]
            live_pool = list(live)
            for v in shown_items:
                hit = next((lv for lv in live_pool if _scalars_equal(v, lv)), None)
                if hit is None:
                    diffs.append(Diff(f"{path}[]", v, "<missing>"))
                else:
                    live_pool.remove(hit)
            return diffs
        for i, v in enumerate(shown):
            if v == ELLIPSIS:
                continue
            if i >= len(live):
                diffs.append(Diff(f"{path}[{i}]", v, "<missing>"))
                continue
            diffs.extend(compare(v, live[i], f"{path}[{i}]"))
        if diffs and 1 < len(shown) < len(live):
            # head + tail elision (`[a, b, ..., last]` — see trim_response's
            # tail-bucket rule): the last shown item stands for live[-1].
            alt = [d for i, v in enumerate(shown[:-1]) for d in compare(v, live[i], f"{path}[{i}]")]
            alt += compare(shown[-1], live[-1], f"{path}[-1]")
            if not alt:
                return []
        return diffs
    if not _scalars_equal(shown, live):
        diffs.append(Diff(path, shown, live))
    return diffs


def is_empty_response(live: Any) -> bool:
    """Live result looks like nothing matched — likely fabricated inputs."""
    if not isinstance(live, dict):
        return False
    if live.get("total_matching") == 0:
        return True
    results = live.get("results")
    if results == [] and live.get("total_matching") is None:
        # no total_matching to lean on — empty results is the signal
        return True
    return False


def shown_expects_empty(shown: Any) -> bool:
    """The hand-authored block itself documents an empty result (a deliberate
    'no match' example) — then an empty live result is not suspicious."""
    if not isinstance(shown, dict):
        return False
    return (
        shown.get("total_matching") == 0
        or shown.get("returned") == 0
        or shown.get("results") == []
    )


# ---------------------------------------------------------------------------
# Live execution (in-memory FastMCP client)
# ---------------------------------------------------------------------------

class LiveRunner:
    """Call MCP tools in-process through ``fastmcp.Client(server.mcp)``.

    Uses the real server object, so tool defaults / envelope shaping /
    SparseRow stripping are exactly what an MCP caller sees. One client
    (one lifespan → one Neo4j connection) for the whole run.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._client = None
        self._cm = None

    def __enter__(self) -> LiveRunner:
        logging.disable(logging.INFO)  # fastmcp's rich handler echoes every ctx.info
        from fastmcp import Client
        from multiomics_explorer.mcp_server.server import mcp

        self._cm = Client(mcp)
        self._client = self._loop.run_until_complete(self._cm.__aenter__())
        return self

    def __exit__(self, *exc) -> None:
        if self._cm is not None:
            self._loop.run_until_complete(self._cm.__aexit__(*exc))
        self._loop.close()

    def call(self, tool: str, kwargs: dict[str, Any]) -> Any:
        """Return the tool's structured (JSON-shaped) result; raises on tool error."""
        result = self._loop.run_until_complete(
            self._client.call_tool(tool, kwargs, raise_on_error=True)
        )
        if result.structured_content is not None:
            return result.structured_content
        # non-object return — fall back to the text content
        return json.loads(result.content[0].text) if result.content else None


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    example: Example
    status: str
    diffs: list[Diff] = field(default_factory=list)
    message: str = ""
    live: Any = None

    def describe(self) -> str:
        head = f"[{self.status:<11}] {self.example.id}"
        if self.message:
            head += f" — {self.message}"
        if self.diffs:
            head += "\n" + "\n".join(f"      {d}" for d in self.diffs)
        return head


def check_example(ex: Example, runner: LiveRunner) -> CheckResult:
    """Run one example against the live KG and classify it."""
    reason = ex.skip_reason
    if reason:
        return CheckResult(ex, STATUS_SKIPPED, message=reason)
    try:
        tool, kwargs = parse_call(ex.call or "")
    except ValueError as e:
        return CheckResult(ex, STATUS_ERROR, message=str(e))
    try:
        live = runner.call(tool, kwargs)
    except Exception as e:  # ToolError / validation / transport
        return CheckResult(ex, STATUS_ERROR, message=f"{type(e).__name__}: {e}")
    shown = parse_shown_response(ex.response or "")
    if is_empty_response(live) and not shown_expects_empty(shown):
        return CheckResult(ex, STATUS_EMPTY, message="live result is empty", live=live)
    if shown is None:
        return CheckResult(ex, STATUS_UNPARSEABLE, message="shown response block could not be parsed", live=live)
    diffs = compare(shown, live)
    if diffs:
        return CheckResult(ex, STATUS_DRIFT, diffs=diffs, live=live)
    return CheckResult(ex, STATUS_OK, live=live)


# ---------------------------------------------------------------------------
# Write: deterministic trim + text-level YAML replacement
# ---------------------------------------------------------------------------

@dataclass
class TrimConfig:
    """Caps applied by :func:`trim_response` (CLI-overridable).

    * ``max_rows`` — ``results`` rows kept (then a bare ``...``)
    * ``max_items`` — entries kept in every other list, at any depth
      (``by_*`` / ``top_*`` rollups, ``not_found``, ``ec_numbers`` …)
    * ``max_dict_keys`` — entries kept in a *mapping-valued* envelope field
      (a dict-valued top-level key such as ``stereo_forms_added`` or a
      ``by_*`` dict); the rest collapse into one ``"...": "+N more"`` entry.
      Row / rollup-entry dicts are never key-capped (their keys are the
      schema's field names).
    * ``min_nulls_to_elide`` — a dict inside a list (a result row or rollup
      entry) with at least this many ``null`` fields drops them and gets one
      ``"...": "N null fields omitted (names…)"`` entry instead (polymorphic rows
      carry many cross-arm nulls). Fewer nulls are shown as-is.
    * ``max_wide_items`` / ``wide_entry_keys`` — a non-``results`` list whose
      entries are dicts with more than ``wide_entry_keys`` fields (``top_genes``,
      ``by_metabolite`` …) keeps only ``max_wide_items`` exemplar entries.
    * ``min_empty_to_elide`` — when at least this many top-level envelope
      fields are ``null`` / ``[]`` / ``{}`` (the empty arms of a polymorphic
      envelope), they collapse into one ``"...": "N empty fields omitted (names…)"``
      entry at the first one's position. Fields in :data:`KEEP_EMPTY_KEYS`
      (``results``, ``not_found``, ``not_matched`` …) are always shown.
    * ``max_string_len`` — longer strings are cut and end in ``...``.
    """

    max_rows: int = MAX_RESULT_ROWS
    max_items: int = MAX_ROLLUP_ITEMS
    max_dict_keys: int = MAX_DICT_KEYS
    min_nulls_to_elide: int = MIN_NULLS_TO_ELIDE
    max_string_len: int = MAX_STRING_LEN
    max_wide_items: int = MAX_WIDE_ITEMS
    wide_entry_keys: int = WIDE_ENTRY_KEYS
    min_empty_to_elide: int = MIN_EMPTY_TO_ELIDE


# Envelope keys whose empty value is the point of many examples.
KEEP_EMPTY_KEYS = frozenset({
    "results", "returned", "total_matching", "truncated",
    "not_found", "not_matched",
})

DEFAULT_TRIM = TrimConfig()


def _elide_str(s: str, max_len: int = MAX_STRING_LEN) -> str:
    return s if len(s) <= max_len else s[: max_len - len(ELLIPSIS)] + ELLIPSIS


def _elide_nulls(d: dict, cfg: TrimConfig) -> dict:
    nulls = [k for k, v in d.items() if v is None]
    if len(nulls) < cfg.min_nulls_to_elide:
        return d
    out = {k: v for k, v in d.items() if v is not None}
    out[ELLIPSIS] = _elision_note(len(nulls), "null", nulls)
    return out


def _elision_note(n: int, kind: str, names: list) -> str:
    """``"3 null fields omitted (a, b, c)"`` — names listed when there are at
    most :data:`MAX_NAMED_ELISIONS` of them, else just the count."""
    note = f"{n} {kind} fields omitted"
    if n <= MAX_NAMED_ELISIONS:
        note += " (" + ", ".join(str(x) for x in names) + ")"
    return note


def _trim_value(v: Any, cfg: TrimConfig, *, in_list: bool = False) -> Any:
    if isinstance(v, str):
        return _elide_str(v, cfg.max_string_len)
    if isinstance(v, dict):
        out = {k: _trim_value(x, cfg) for k, x in v.items()}
        return _elide_nulls(out, cfg) if in_list else out
    if isinstance(v, list):
        cap = cfg.max_items
        if v and all(isinstance(x, dict) and len(x) > cfg.wide_entry_keys for x in v):
            cap = min(cap, cfg.max_wide_items)
        items = [_trim_value(x, cfg, in_list=True) for x in v[:cap]]
        if len(v) <= cap:
            return items
        items.append(ELLIPSIS)
        if _is_tail_bucket(v[-1]):
            items.append(_trim_value(v[-1], cfg, in_list=True))
        return items
    return v


# Rollup tail buckets that docs tell the reader to look at (the KEGG-class
# breakdowns end with a "not classified" entry): kept after the ``...``.
TAIL_BUCKET_VALUES = frozenset({"not classified"})


def _is_tail_bucket(x: Any) -> bool:
    return isinstance(x, dict) and any(
        isinstance(val, str) and val in TAIL_BUCKET_VALUES for val in x.values()
    )


def _is_empty(v: Any) -> bool:
    return v is None or v == [] or v == {}


def _cap_mapping(d: dict, cfg: TrimConfig) -> dict:
    if len(d) <= cfg.max_dict_keys:
        return d
    out = dict(list(d.items())[: cfg.max_dict_keys])
    out[ELLIPSIS] = f"+{len(d) - cfg.max_dict_keys} more"
    return out


def trim_response(
    live: Any, cfg: TrimConfig = DEFAULT_TRIM, keep: tuple[str, ...] = (),
) -> Any:
    """Deterministic trim of a live envelope for display (see :class:`TrimConfig`).

    * top-level scalars kept as-is (strings > ``max_string_len`` elided)
    * ``results`` → first ``max_rows`` rows + ``...``
    * every other list, at any depth → first ``max_items`` entries + ``...``
      (+ the last entry when it is a ``"not classified"`` tail bucket;
      :func:`compare` accepts that head + tail form)
    * dict-valued envelope fields → first ``max_dict_keys`` entries
    * dicts inside lists with ≥ ``min_nulls_to_elide`` nulls → nulls dropped
      behind one ``"...": "N null fields omitted (names…)"`` entry
    * non-results lists of wide dicts → ``max_wide_items`` exemplar entries
    * ≥ ``min_empty_to_elide`` empty top-level fields → one ``"..."`` entry
    * ``keep`` (an example's ``keep:`` list) — envelope keys shown whole: never
      dict-capped, never folded into the empty-fields entry

    Elisions are ``...`` list items and ``"..."`` keys only, so every real
    key stays a real field name and :func:`parse_shown_response` drops the
    markers; the output is a subset of ``live`` (``--check`` passes on it).
    Idempotent per live result: re-running on an unchanged KG rewrites the
    same text.
    """
    if not isinstance(live, dict):
        return _trim_value(live, cfg)
    empties = [
        k for k, v in live.items()
        if _is_empty(v) and k not in KEEP_EMPTY_KEYS and k not in keep
    ]
    elide_empties = len(empties) >= cfg.min_empty_to_elide
    out: dict[str, Any] = {}
    for k, v in live.items():
        if elide_empties and k in empties:
            if k == empties[0]:
                out[ELLIPSIS] = _elision_note(len(empties), "empty", empties)
            continue
        if k == "results" and isinstance(v, list):
            rows = [_trim_value(x, cfg, in_list=True) for x in v[: cfg.max_rows]]
            out[k] = rows + [ELLIPSIS] if len(v) > cfg.max_rows else rows
        elif isinstance(v, dict):
            trimmed = _trim_value(v, cfg)
            out[k] = trimmed if k in keep else _cap_mapping(trimmed, cfg)
        else:
            out[k] = _trim_value(v, cfg)
    return out


INLINE_WIDTH = 110


def _dump_scalar(v: Any) -> str:
    if v == ELLIPSIS:
        return ELLIPSIS
    return json.dumps(v, ensure_ascii=False, default=str)


def _dump(v: Any, indent: int) -> str:
    """JSON with a compact rule: a nested dict/list whose one-line form fits
    in ``INLINE_WIDTH`` stays on one line (the hand-authored style); otherwise
    one entry per line at ``indent``. The top-level envelope is always
    multi-line."""
    if not isinstance(v, (dict, list)):
        return _dump_scalar(v)
    if not v:
        return "{}" if isinstance(v, dict) else "[]"
    pad = "  " * (indent + 1)
    close = "  " * indent
    if isinstance(v, dict):
        items = [f"{json.dumps(str(k), ensure_ascii=False)}: {_dump(x, indent + 1)}" for k, x in v.items()]
        one_line = "{" + ", ".join(items) + "}"
        if indent > 0 and "\n" not in one_line and len(one_line) + 2 * indent <= INLINE_WIDTH:
            return one_line
        return "{\n" + ",\n".join(pad + it for it in items) + "\n" + close + "}"
    items = [_dump(x, indent + 1) for x in v]
    one_line = "[" + ", ".join(items) + "]"
    if "\n" not in one_line and len(one_line) + 2 * indent <= INLINE_WIDTH:
        return one_line
    return "[\n" + ",\n".join(pad + it for it in items) + "\n" + close + "]"


def format_response(
    live: Any, cfg: TrimConfig = DEFAULT_TRIM, keep: tuple[str, ...] = (),
) -> str:
    """JSON-ish text of the trimmed envelope: two-space indent, short
    dicts/lists inline, ``...`` items rendered bare (parseable back by
    :func:`parse_shown_response`)."""
    return _dump(trim_response(live, cfg, keep), 0)


_EXAMPLES_KEY_RE = re.compile(r"^examples:\s*$", re.MULTILINE)


def _example_item_starts(text: str) -> list[int]:
    """Line offsets (char positions) of each ``  - `` item under ``examples:``."""
    m = _EXAMPLES_KEY_RE.search(text)
    if not m:
        return []
    starts: list[int] = []
    pos = m.end()
    for line_m in re.finditer(r"^(\S.*)?$|^  - .*$", text[pos:], re.MULTILINE):
        if line_m.group(0).startswith("  - "):
            starts.append(pos + line_m.start())
        elif line_m.group(1):  # next top-level key → end of examples list
            break
    return starts


def replace_response_block(text: str, index: int, new_body: str) -> str:
    """Return ``text`` with the ``response: |`` block of example ``index``
    replaced by ``new_body`` (re-indented). Everything else byte-identical.
    Raises if the example has no literal ``response: |`` block.
    """
    starts = _example_item_starts(text)
    if index >= len(starts):
        raise ValueError(f"example index {index} out of range ({len(starts)} items)")
    item_start = starts[index]
    item_end = starts[index + 1] if index + 1 < len(starts) else _examples_end(text, item_start)
    item = text[item_start:item_end]
    m = re.search(r"^(?P<indent>[ ]+)response:\s*\|[-+]?\s*\n", item, re.MULTILINE)
    if not m:
        raise ValueError(f"example {index} has no `response: |` block")
    key_indent = m.group("indent")
    body_start = m.end()
    # block body = following lines indented deeper than the key (or blank)
    body_re = re.compile(rf"^(?:{key_indent} +.*|[ \t]*)$", re.MULTILINE)
    pos = body_start
    body_end = body_start
    while pos < len(item):
        line_end = item.find("\n", pos)
        line_end = len(item) if line_end == -1 else line_end
        line = item[pos:line_end]
        if not body_re.match(line):
            break
        if line.strip():
            body_end = line_end + 1 if line_end < len(item) else line_end
        pos = line_end + 1
    body_indent = key_indent + "  "
    new_block = "".join(f"{body_indent}{ln}\n" if ln.strip() else "\n" for ln in new_body.rstrip("\n").split("\n"))
    new_item = item[:body_start] + new_block + item[body_end:]
    return text[:item_start] + new_item + text[item_end:]


def _examples_end(text: str, after: int) -> int:
    m = re.search(r"^\S", text[after:], re.MULTILINE)
    return len(text) if not m else after + m.start()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_check(paths: list[Path], runner: LiveRunner, *, verbose: bool = True) -> list[CheckResult]:
    results: list[CheckResult] = []
    for path in paths:
        for ex in load_examples(path):
            r = check_example(ex, runner)
            results.append(r)
            if verbose and r.status != STATUS_SKIPPED:
                print(r.describe())
    return results


def summarize(results: list[CheckResult]) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    order = [STATUS_OK, STATUS_DRIFT, STATUS_ERROR, STATUS_EMPTY, STATUS_UNPARSEABLE, STATUS_SKIPPED]
    parts = [f"{s}={counts.get(s, 0)}" for s in order]
    return f"examples={len(results)} " + " ".join(parts)


def run_write(paths: list[Path], runner: LiveRunner, cfg: TrimConfig = DEFAULT_TRIM) -> int:
    """Rewrite response blocks from live; returns number of blocks rewritten."""
    written = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for ex in load_examples(path):
            if ex.skip_reason:
                continue
            try:
                tool, kwargs = parse_call(ex.call or "")
                live = runner.call(tool, kwargs)
            except Exception as e:
                print(f"[error      ] {ex.id} — {type(e).__name__}: {e} (left untouched)")
                continue
            if is_empty_response(live) and not shown_expects_empty(parse_shown_response(ex.response or "")):
                print(f"[empty      ] {ex.id} — live result is empty (left untouched; fix the inputs)")
                continue
            try:
                text = replace_response_block(text, ex.index, format_response(live, cfg, ex.keep))
            except ValueError as e:
                print(f"[unwritable ] {ex.id} — {e}")
                continue
            written += 1
            print(f"[written    ] {ex.id}")
        path.write_text(text, encoding="utf-8")
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare shown responses with live (default)")
    mode.add_argument("--write", nargs="*", metavar="TOOL", help="rewrite response blocks from live (optionally only these tools)")
    ap.add_argument("--tool", action="append", help="scope to this tool YAML (repeatable)")
    ap.add_argument("--quiet", action="store_true", help="only print the summary + failures")
    ap.add_argument("--max-rows", type=int, default=MAX_RESULT_ROWS, help="--write: results rows kept (default %(default)s)")
    ap.add_argument("--max-items", type=int, default=MAX_ROLLUP_ITEMS, help="--write: entries kept in other lists (default %(default)s)")
    ap.add_argument("--max-dict-keys", type=int, default=MAX_DICT_KEYS, help="--write: entries kept in dict-valued envelope fields (default %(default)s)")
    ap.add_argument("--min-nulls", type=int, default=MIN_NULLS_TO_ELIDE, help="--write: elide a row's nulls when it has at least this many (default %(default)s)")
    args = ap.parse_args(argv)
    cfg = TrimConfig(
        max_rows=args.max_rows,
        max_items=args.max_items,
        max_dict_keys=args.max_dict_keys,
        min_nulls_to_elide=args.min_nulls,
    )

    tools = list(args.tool or [])
    if args.write:
        tools.extend(args.write)
    paths = iter_tool_yamls(tools or None)

    with LiveRunner() as runner:
        if args.write is not None:
            n = run_write(paths, runner, cfg)
            print(f"rewrote {n} response block(s) in {len(paths)} file(s)")
            return 0
        results = run_check(paths, runner, verbose=not args.quiet)

    if args.quiet:
        for r in results:
            if r.status in FAILING_STATUSES:
                print(r.describe())
    print()
    print(summarize(results))
    return 1 if any(r.status in FAILING_STATUSES for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
