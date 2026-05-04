"""Smoke tests for examples/*.py — run each scenario against the live KG."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.kg

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# --- pathway_enrichment.py ---

PATHWAY_SCRIPT = REPO_ROOT / "examples" / "pathway_enrichment.py"

PATHWAY_SCENARIOS = ["landscape", "de", "cluster", "custom"]
# "ortholog" is a placeholder in the script and is skipped until real
# group-id plumbing lands.


@pytest.mark.parametrize("scenario", PATHWAY_SCENARIOS)
def test_scenario_runs_cleanly(scenario):
    """Each pathway_enrichment scenario exits 0 and produces some output on the live KG."""
    cmd = [sys.executable, str(PATHWAY_SCRIPT), "--scenario", scenario]
    if scenario == "custom":
        cmd += ["--locus-tags", "PMM0001,PMM0002,PMM0003"]
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, (
        f"scenario {scenario} failed: stderr={result.stderr}"
    )
    assert result.stdout.strip(), f"scenario {scenario} produced no output"


# --- metabolites.py ---

METABOLITES_SCRIPT = REPO_ROOT / "examples" / "metabolites.py"

METABOLITES_SCENARIOS = [
    "discover",
    "compound_to_genes",
    "gene_to_metabolites",
    "cross_feeding",
    "n_source_de",
    "tcdb_chain",
    "precision_tier",
    "measurement",
]


@pytest.mark.parametrize("scenario", METABOLITES_SCENARIOS)
def test_metabolites_scenario_runs_cleanly(scenario):
    """Each metabolites.py scenario exits 0 and produces some output on the live KG."""
    cmd = [sys.executable, str(METABOLITES_SCRIPT), "--scenario", scenario]
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, (
        f"metabolites scenario {scenario} failed: stderr={result.stderr}"
    )
    assert result.stdout.strip(), (
        f"metabolites scenario {scenario} produced no output"
    )
