"""User-facing text must not leak internal build shorthand.

Tool docstrings, Pydantic field descriptions and the about-content yaml are
served to MCP clients; references like "PR 3b" or "slice 4" mean nothing
there. Code comments (`# ...`) are exempt (backlog 2.7).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "multiomics_explorer"
FILES = sorted(
    [ROOT / "mcp_server" / "tools.py", ROOT / "api" / "functions.py",
     ROOT / "kg" / "queries_lib.py", ROOT / "kg" / "queries.py"]
    + list((ROOT / "inputs").rglob("*.yaml"))
    + list((ROOT / "skills").rglob("*.md"))
)
# "PR 3", "PR3b", "slice 4", "slice 2a" — but not "slice 0.012" (a numeric
# range) or "slice 10x" style tokens.
SHORTHAND = re.compile(r"\b(?:PR|slice)\s?\d[ab]?\b(?![.\d])")


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_internal_shorthand(path: Path):
    bad = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        code = line.split("#", 1)[0] if path.suffix == ".py" else line
        if SHORTHAND.search(code):
            bad.append(f"{path.name}:{i}: {line.strip()[:100]}")
    assert not bad, "internal shorthand in user-facing text:\n" + "\n".join(bad)
