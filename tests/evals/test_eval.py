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

from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_find_gene,
    build_resolve_gene,
    build_get_gene_details_main,
    build_get_homologs,
    build_homolog_expression,
    build_query_expression,
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
    "find_gene": build_find_gene,
    "get_gene_details": build_get_gene_details_main,
    "query_expression": build_query_expression,
    "compare_conditions": build_compare_conditions,
    "get_homologs": build_get_homologs,
}


def run_case(conn, tool: str, params: dict) -> list[dict]:
    """Execute a case using the shared query builders."""
    if tool == "raw_cypher":
        return conn.execute_query(params["query"])

    if tool == "get_homologs_with_expression":
        cypher, query_params = build_get_homologs(gene_id=params["gene_id"])
        homologs = conn.execute_query(cypher, **query_params)
        if not homologs:
            return []
        all_ids = [params["gene_id"]] + [h["locus_tag"] for h in homologs]
        cypher_expr, params_expr = build_homolog_expression(gene_ids=all_ids)
        return conn.execute_query(cypher_expr, **params_expr)

    builder = TOOL_BUILDERS[tool]
    cypher, query_params = builder(**params)
    return conn.execute_query(cypher, **query_params)


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
    check_expectations(results, expect, case["id"])
