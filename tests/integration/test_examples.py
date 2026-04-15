"""Smoke test for examples/pathway_enrichment.py — run each scenario."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.kg

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "examples" / "pathway_enrichment.py"

SCENARIOS = ["landscape", "de", "cluster", "custom"]
# "ortholog" is a placeholder in the script and is skipped until real
# group-id plumbing lands.


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_runs_cleanly(scenario):
    """Each scenario exits 0 and produces some output on the live KG."""
    cmd = [sys.executable, str(SCRIPT), "--scenario", scenario]
    if scenario == "custom":
        cmd += ["--locus-tags", "PMM0001,PMM0002,PMM0003"]
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, (
        f"scenario {scenario} failed: stderr={result.stderr}"
    )
    assert result.stdout.strip(), f"scenario {scenario} produced no output"
