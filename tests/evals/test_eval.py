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

from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_gene_ontology_terms,
    build_gene_overview,
    build_gene_stub,
    build_genes_by_ontology,
    build_get_gene_details,
    build_get_homologs_groups,
    build_list_condition_types,
    build_list_gene_categories,
    build_list_organisms,
    build_query_expression,
    build_resolve_gene,
    build_search_genes,
    build_search_genes_dedup_groups,
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
    "search_genes": build_search_genes,
    "gene_overview": build_gene_overview,
    "get_gene_details": build_get_gene_details,
    "query_expression": build_query_expression,
    "compare_conditions": build_compare_conditions,
    "get_homologs": build_get_homologs_groups,
    "list_organisms": build_list_organisms,
    "search_ontology": build_search_ontology,
    "genes_by_ontology": build_genes_by_ontology,
    "gene_ontology_terms": build_gene_ontology_terms,
}


def run_case(conn, tool: str, params: dict) -> list[dict]:
    """Execute a case using the shared query builders."""
    if tool == "raw_cypher":
        return conn.execute_query(params["query"])

    if tool == "list_filter_values":
        cat_cypher, cat_params = build_list_gene_categories()
        categories = conn.execute_query(cat_cypher, **cat_params)
        cond_cypher, cond_params = build_list_condition_types()
        condition_types = conn.execute_query(cond_cypher, **cond_params)
        # Return combined list so check_expectations can count rows
        return categories + condition_types

    if tool == "get_homologs_with_members":
        cypher_groups, params_groups = build_get_homologs_groups(gene_id=params["gene_id"])
        return conn.execute_query(cypher_groups, **params_groups)

    builder = TOOL_BUILDERS[tool]
    deduplicate = params.get("deduplicate", False)
    # Strip tool-level params that aren't accepted by query builders
    builder_params = {k: v for k, v in params.items() if k != "deduplicate"}
    # gene_overview: map gene_ids -> locus_tags for the query builder
    if tool == "gene_overview" and "gene_ids" in builder_params:
        builder_params["locus_tags"] = builder_params.pop("gene_ids")
    cypher, query_params = builder(**builder_params)
    results = conn.execute_query(cypher, **query_params)

    # get_gene_details returns g{.*} AS gene — unwrap for flat column checks
    if tool == "get_gene_details" and results and "gene" in results[0]:
        results = [r["gene"] for r in results if r.get("gene") is not None]

    if deduplicate and tool == "search_genes":
        locus_tags = [r["locus_tag"] for r in results]
        dedup_cypher, dedup_params = build_search_genes_dedup_groups(
            locus_tags=locus_tags,
        )
        dedup_rows = conn.execute_query(dedup_cypher, **dedup_params)
        tag_to_group = {r["locus_tag"]: r["dedup_group"] for r in dedup_rows}
        seen_groups: set[str] = set()
        deduped = []
        for row in results:
            group = tag_to_group.get(row["locus_tag"])
            if group:
                if group in seen_groups:
                    continue
                seen_groups.add(group)
            deduped.append(row)
        results = deduped

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
