"""Source-level audit: no stale boolean literal on a two-state KG property.

The KG stores eight boolean-like properties as named string pairs
(`kg/constants.py::TWO_STATE`), never 'true'/'false' (KG hand-off
2026-08-28, HO-001). A stale literal does not error — it silently returns
0 rows or `false` — so this test scans the explorer's source for every
Cypher / Python comparison on those properties and requires the literal to
be one of the vocabulary's two values.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from multiomics_explorer.kg.constants import TWO_STATE, two_state

PKG = Path(__file__).resolve().parents[2] / "multiomics_explorer"
SCAN_FILES = sorted(
    list((PKG / "kg").glob("*.py"))
    + list((PKG / "api").glob("*.py"))
    + list((PKG / "mcp_server").glob("*.py"))
)
PROPS = "|".join(re.escape(p) for p in TWO_STATE)
# `<alias>.<prop> <op> '<literal>'`  (Cypher, either quote style, = / <> / IN)
CYPHER_CMP = re.compile(
    rf"\b(?:\w+\.)?({PROPS})\s*(?:=|<>)\s*\\?['\"]([A-Za-z_]+)\\?['\"]"
)
# Python-side comparisons on a row value: r["is_time_course"] == "true"
PY_CMP = re.compile(
    rf"\[\s*['\"]({PROPS})['\"]\s*\]\s*(?:==|!=)\s*['\"]([A-Za-z_]+)['\"]"
)
# Param coercions: params["rankable_str"] = "true" if ...
PARAM_COERCE = re.compile(
    rf"({PROPS})_str[\"']\]\s*=\s*['\"]([A-Za-z_]+)['\"]"
)
STALE = re.compile(r"['\"](?:true|false)['\"]")


def _allowed(prop: str) -> set[str]:
    return set(TWO_STATE[prop])


def test_two_state_helper_maps_positive_and_negative():
    for prop, (pos, neg) in TWO_STATE.items():
        assert two_state(prop, True) == pos
        assert two_state(prop, False) == neg
        assert pos != neg and "true" not in (pos, neg) and "false" not in (pos, neg)


@pytest.mark.parametrize("path", SCAN_FILES, ids=lambda p: p.name)
def test_no_stale_literal_on_two_state_property(path: Path):
    src = path.read_text()
    bad: list[str] = []
    for pat in (CYPHER_CMP, PY_CMP, PARAM_COERCE):
        for m in pat.finditer(src):
            prop, lit = m.group(1), m.group(2)
            if lit not in _allowed(prop):
                line = src.count("\n", 0, m.start()) + 1
                bad.append(f"{path.name}:{line}: {m.group(0)!r} (allowed {sorted(_allowed(prop))})")
    assert not bad, "stale two-state literals:\n" + "\n".join(bad)


@pytest.mark.parametrize("path", SCAN_FILES, ids=lambda p: p.name)
def test_no_true_false_string_near_two_state_property(path: Path):
    """Coarser net: a 'true'/'false' string on the same source line as one
    of the eight property names. `is_uninformative` / `level_is_best_effort`
    are genuinely 'true'-valued and are not two-state properties."""
    names = re.compile(rf"\b({PROPS})\b")
    bad = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if STALE.search(line) and names.search(line):
            bad.append(f"{path.name}:{i}: {line.strip()[:120]}")
    assert not bad, "'true'/'false' next to a two-state property:\n" + "\n".join(bad)
