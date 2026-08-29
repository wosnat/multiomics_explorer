"""Live-KG checks for the doc-lint data files (``-m kg``).

- ``test_vocab_snapshot_matches_live`` — ``inputs/lint/vocab_snapshot.yaml``
  equals the live ``ControlledVocabulary`` nodes. Fails after a KG rebuild
  that changes a vocabulary; fix by running ``scripts/snapshot_vocab.py``.
- ``test_kg_claims_register`` — every entry of ``inputs/lint/kg_claims.yaml``
  evaluates to its ``expect`` value (within ``tolerance``). A failure names
  the ``used_in`` files whose prose quotes the number.

These are NOT fixture tests: when a claim fails, the docs (or the register's
expected value, if the change is intended) get updated — never the assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.snapshot_vocab import SNAPSHOT_PATH, load_snapshot, snapshot_vocab

pytestmark = pytest.mark.kg

REPO = Path(__file__).resolve().parents[2]
CLAIMS_PATH = REPO / "multiomics_explorer" / "inputs" / "lint" / "kg_claims.yaml"


def _load_claims() -> list[dict]:
    return yaml.safe_load(CLAIMS_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Vocabulary snapshot
# ---------------------------------------------------------------------------


def test_vocab_snapshot_matches_live(conn):
    live = snapshot_vocab(conn)
    stored = load_snapshot()
    if stored == live:
        return
    diffs = []
    if stored.get("kg_built_at") != live.get("kg_built_at"):
        diffs.append(f"kg_built_at: snapshot {stored.get('kg_built_at')} vs live {live.get('kg_built_at')}")
    s_v, l_v = stored["vocabularies"], live["vocabularies"]
    for prop in sorted(set(s_v) | set(l_v)):
        s_by, l_by = s_v.get(prop, {}), l_v.get(prop, {})
        for applies in sorted(set(s_by) | set(l_by)):
            sv = set((s_by.get(applies) or {}).get("values", []))
            lv = set((l_by.get(applies) or {}).get("values", []))
            if sv != lv:
                diffs.append(
                    f"{prop} / {applies}: +{sorted(lv - sv)} -{sorted(sv - lv)}"
                )
    pytest.fail(
        f"{SNAPSHOT_PATH.relative_to(REPO)} is stale vs the live KG — "
        "run `uv run python scripts/snapshot_vocab.py` and re-check any docs that "
        "quote the changed values (tests/unit/test_docs_lint.py::test_vocab_values_in_docs):\n  "
        + "\n  ".join(diffs)
    )


# ---------------------------------------------------------------------------
# KG-claims register
# ---------------------------------------------------------------------------


def _registry_value(source: str) -> dict:
    if source == "ontology_config":
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG

        return {"ontologies": len(ONTOLOGY_CONFIG)}
    if source == "tool_registry":
        from tests.unit.test_docs_lint import registered_tool_names

        return {"tools": len(registered_tool_names())}
    raise ValueError(f"unknown claim source {source!r}")


def _within(expected, actual, tol: dict) -> bool:
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        return expected == actual
    if actual is None:
        return False
    if "rel" in tol:
        return abs(actual - expected) <= abs(expected) * float(tol["rel"])
    if "abs" in tol:
        return abs(actual - expected) <= float(tol["abs"])
    return actual == expected


@pytest.mark.parametrize("claim", _load_claims(), ids=lambda c: c["id"])
def test_kg_claims_register(conn, claim: dict):
    if claim.get("source"):
        row = _registry_value(claim["source"])
    else:
        rows = conn.execute_query(claim["cypher"], timeout=120)
        assert len(rows) == 1, f"{claim['id']}: cypher must RETURN exactly one row, got {len(rows)}"
        row = rows[0]
    tol = claim.get("tolerance") or {}
    mismatches = []
    for key, expected in claim["expect"].items():
        assert key in row, f"{claim['id']}: cypher does not return column {key!r} (got {sorted(row)})"
        if not _within(expected, row[key], tol):
            mismatches.append(f"{key}: docs say {expected!r}, KG says {row[key]!r}")
    assert not mismatches, (
        f"claim '{claim['id']}' drifted ({claim.get('note', '').strip()}):\n  "
        + "\n  ".join(mismatches)
        + "\n  fix the prose in:\n    "
        + "\n    ".join(claim["used_in"])
        + "\n  then update `expect` in multiomics_explorer/inputs/lint/kg_claims.yaml"
    )
