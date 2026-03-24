"""Eval runner: parameterized tests driven by cases.yaml.

Each case exercises a KG query pattern (matching the MCP tools) and asserts
on result shape, required columns, and expected values.

Requires a live Neo4j instance — all tests are marked with @pytest.mark.kg.

Usage:
    pytest tests/evals/ -v                     # run all evals
    pytest tests/evals/ -v -k resolve_gene      # run gene lookup evals only
"""

from pathlib import Path

import pytest
import yaml

from functools import partial

from multiomics_explorer.api import functions as api
from multiomics_explorer.kg.queries_lib import (
    build_gene_ontology_terms,
    build_gene_overview,
    build_gene_stub,
    build_genes_by_function,
    build_genes_by_ontology,
    build_get_gene_details,
    build_gene_homologs,
    build_list_gene_categories,
    build_list_experiments,
    build_list_experiments_summary,
    build_list_organisms,
    build_list_publications,
    build_resolve_gene,
    build_search_ontology,
)

# ---------------------------------------------------------------------------
# Load cases
# ---------------------------------------------------------------------------

CASES_PATH = Path(__file__).parent / "cases.yaml"
CASES = yaml.safe_load(CASES_PATH.read_text())
CASE_IDS = [c["id"] for c in CASES]

# ---------------------------------------------------------------------------
# Query dispatch via shared builders
# ---------------------------------------------------------------------------

TOOL_BUILDERS = {
    "resolve_gene": build_resolve_gene,
    "genes_by_function": build_genes_by_function,
    "gene_overview": build_gene_overview,
    "get_gene_details": build_get_gene_details,
    "gene_homologs": build_gene_homologs,
    "list_organisms": build_list_organisms,
    "search_ontology": build_search_ontology,
    "genes_by_ontology": build_genes_by_ontology,
    "gene_ontology_terms": build_gene_ontology_terms,
    "list_publications": build_list_publications,
    "list_experiments": build_list_experiments,
    "list_experiments_summary": build_list_experiments_summary,
}


def run_case(conn, tool: str, params: dict) -> list[dict]:
    """Execute a case using the shared query builders."""
    if tool == "raw_cypher":
        return conn.execute_query(params["query"])

    if tool == "list_filter_values":
        return api.list_filter_values(
            filter_type=params.get("filter_type", "gene_category"),
            conn=conn,
        )["results"]

    if tool == "gene_homologs_with_members":
        # Legacy eval case — run detail query for batch locus_tags
        cypher, params_b = build_gene_homologs(locus_tags=params["locus_tags"])
        return conn.execute_query(cypher, **params_b)

    builder = TOOL_BUILDERS[tool]
    limit = params.get("limit")
    # Strip tool-level params that aren't accepted by query builders
    builder_params = {k: v for k, v in params.items() if k not in ("limit",)}
    cypher, query_params = builder(**builder_params)
    results = conn.execute_query(cypher, **query_params)
    # Apply limit at the test level (mirrors MCP layer behavior)
    if limit is not None:
        results = results[:limit]

    # get_gene_details returns g{.*} AS gene — unwrap for flat column checks
    if tool == "get_gene_details" and results and "gene" in results[0]:
        results = [r["gene"] for r in results if r.get("gene") is not None]

    return results


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


def check_expectations(results: list[dict], expect: dict, case_id: str):
    """Verify results against the expect block from a case."""
    min_rows = expect.get("min_rows", 1)
    max_rows = expect.get("max_rows")

    assert len(results) >= min_rows, (
        f"[{case_id}] expected >= {min_rows} rows, got {len(results)}"
    )
    if max_rows is not None:
        assert len(results) <= max_rows, (
            f"[{case_id}] expected <= {max_rows} rows, got {len(results)}"
        )

    if not results:
        return

    # Check required columns
    if "columns" in expect:
        actual_cols = set(results[0].keys())
        for col in expect["columns"]:
            assert col in actual_cols, (
                f"[{case_id}] missing column '{col}', have {sorted(actual_cols)}"
            )

    # Check first row values
    if "row0" in expect:
        for key, val in expect["row0"].items():
            assert results[0].get(key) == val, (
                f"[{case_id}] row0['{key}'] = {results[0].get(key)!r}, expected {val!r}"
            )

    # Check that at least one row contains expected values
    if "contains" in expect:
        for key, val in expect["contains"].items():
            found = any(str(r.get(key, "")) == str(val) for r in results)
            assert found, (
                f"[{case_id}] no row has {key}={val!r}"
            )

    # Check row0 expression (e.g. "cnt > 0")
    if "row0_check" in expect:
        row = results[0]
        assert eval(expect["row0_check"], {"__builtins__": {}}, row), (
            f"[{case_id}] row0_check failed: {expect['row0_check']} with {row}"
        )


# ---------------------------------------------------------------------------
# Parameterized test
# ---------------------------------------------------------------------------


@pytest.mark.kg
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_eval(conn, case):
    tool = case["tool"]
    params = case.get("params", {})
    expect = case.get("expect", {})

    results = run_case(conn, tool, params)
    check_expectations(results, expect or {}, case["id"])
