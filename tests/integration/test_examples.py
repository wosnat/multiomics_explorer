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


# --- annotation_evidence.py ---

ANNOTATION_EVIDENCE_SCRIPT = REPO_ROOT / "examples" / "annotation_evidence.py"

# Scenario -> a substring the scenario's own output must contain. Exit code 0
# plus non-empty stdout is not enough: a runnable doc that reads the wrong row
# key still exits 0 and prints `[None, None, None, None]`.
ANNOTATION_EVIDENCE_SCENARIOS = [
    ("merops_call_class", "peptidase"),
    ("tcdb_attachment_depth", "attachment_depth=most_specific"),
    ("interpro_enrichment", "HOMOLOGOUS_SUPERFAMILY"),
    ("trust_filtered_tcdb", "evidence_score"),
]


@pytest.mark.parametrize(
    "scenario,expected", ANNOTATION_EVIDENCE_SCENARIOS,
    ids=[s for s, _ in ANNOTATION_EVIDENCE_SCENARIOS],
)
def test_annotation_evidence_scenario_runs_cleanly(scenario, expected):
    """Each annotation_evidence.py scenario exits 0 and prints the fact it
    exists to demonstrate, on the live KG."""
    cmd = [sys.executable, str(ANNOTATION_EVIDENCE_SCRIPT), "--scenario", scenario]
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=300
    )
    assert result.returncode == 0, (
        f"annotation_evidence scenario {scenario} failed: stderr={result.stderr}"
    )
    assert result.stdout.strip(), (
        f"annotation_evidence scenario {scenario} produced no output"
    )
    assert expected in result.stdout, (
        f"annotation_evidence scenario {scenario} printed no {expected!r}:\n"
        f"{result.stdout}"
    )
