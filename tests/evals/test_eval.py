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
    build_differential_expression_by_gene,
    build_gene_derived_metrics,
    build_gene_derived_metrics_summary,
    build_gene_ontology_terms,
    build_gene_overview,
    build_gene_stub,
    build_genes_by_function,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_summary,
    build_genes_by_numeric_metric,
    build_gene_details,
    build_gene_homologs,
    build_list_derived_metrics,
    build_list_gene_categories,
    build_list_experiments,
    build_list_experiments_summary,
    build_genes_by_metabolite_metabolism,
    build_list_metabolite_assays,
    build_list_metabolites,
    build_list_organisms,
    build_metabolites_by_quantifies_assay,
    build_metabolites_by_quantifies_assay_summary,
    build_metabolites_by_flags_assay,
    build_metabolites_by_flags_assay_summary,
    build_assays_by_metabolite,
    build_assays_by_metabolite_summary,
    build_list_publications,
    build_resolve_gene,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
    build_search_ontology,
    build_differential_expression_by_ortholog_results,
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
    "gene_details": build_gene_details,
    "gene_homologs": build_gene_homologs,
    "list_organisms": build_list_organisms,
    "search_ontology": build_search_ontology,
    # genes_by_ontology / ontology_landscape: dispatched via api (L2) —
    # compose envelopes from multiple queries; can't be reduced to a single
    # (cypher, params) tuple.
    "genes_by_ontology": None,
    "ontology_landscape": None,
    "gene_ontology_terms": build_gene_ontology_terms,
    "list_publications": build_list_publications,
    "list_metabolites": build_list_metabolites,
    "list_metabolite_assays": build_list_metabolite_assays,
    "genes_by_metabolite": build_genes_by_metabolite_metabolism,
    "metabolites_by_quantifies_assay": build_metabolites_by_quantifies_assay,
    "metabolites_by_quantifies_assay_summary": build_metabolites_by_quantifies_assay_summary,
    "metabolites_by_flags_assay": build_metabolites_by_flags_assay,
    "metabolites_by_flags_assay_summary": build_metabolites_by_flags_assay_summary,
    "assays_by_metabolite": build_assays_by_metabolite,
    "assays_by_metabolite_summary": build_assays_by_metabolite_summary,
    "list_experiments": build_list_experiments,
    "list_experiments_summary": build_list_experiments_summary,
    "list_derived_metrics": build_list_derived_metrics,
    "gene_derived_metrics": build_gene_derived_metrics,
    "gene_derived_metrics_summary": build_gene_derived_metrics_summary,
    "genes_by_numeric_metric": build_genes_by_numeric_metric,
    "differential_expression_by_gene": build_differential_expression_by_gene,
    "search_homolog_groups": build_search_homolog_groups,
    "search_homolog_groups_summary": build_search_homolog_groups_summary,
    "genes_by_homolog_group": build_genes_by_homolog_group,
    "genes_by_homolog_group_summary": build_genes_by_homolog_group_summary,
    "differential_expression_by_ortholog": build_differential_expression_by_ortholog_results,
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

    if tool == "genes_by_ontology":
        # Dispatch via api (L2) — composes envelope; eval cases assert on rows.
        limit = params.get("limit")
        api_params = {k: v for k, v in params.items() if k != "limit"}
        if limit is not None:
            api_params["limit"] = limit
        return api.genes_by_ontology(**api_params, conn=conn).get("results", [])

    if tool == "ontology_landscape":
        limit = params.get("limit")
        api_params = {k: v for k, v in params.items() if k != "limit"}
        if limit is not None:
            api_params["limit"] = limit
        return api.ontology_landscape(**api_params, conn=conn).get("results", [])

    if tool == "pathway_enrichment":
        limit = params.get("limit")
        api_params = {k: v for k, v in params.items() if k != "limit"}
        if limit is not None:
            api_params["limit"] = limit
        return api.pathway_enrichment(**api_params, conn=conn).to_envelope().get("results", [])

    if tool == "gene_overview":
        # Dispatch via api (L2) — derived_metric_count + value_kinds are
        # synthesized from per-kind builder counts at the api layer; the
        # raw builder doesn't expose those fields.
        return api.gene_overview(**params, conn=conn).get("results", [])

    if tool == "genes_by_numeric_metric":
        # Dispatch via api (L2) — detail builder requires resolved
        # derived_metric_ids; api handles metric_types → ID resolution +
        # gate validation. Eval cases assert on rows.
        return api.genes_by_numeric_metric(**params, conn=conn).get("results", [])

    if tool == "genes_by_boolean_metric":
        return api.genes_by_boolean_metric(**params, conn=conn).get("results", [])

    if tool == "genes_by_categorical_metric":
        return api.genes_by_categorical_metric(**params, conn=conn).get("results", [])

    if tool == "list_metabolites":
        # Dispatch via api (L2) — organism_names lowercasing + summary/detail
        # split + not_found computation live above the builder.
        return api.list_metabolites(**params, conn=conn).get("results", [])

    if tool == "genes_by_metabolite":
        # Dispatch via api (L2) — two-arm dispatch + global sort + slice
        # + not_found / not_matched + auto-warning live above the builders.
        return api.genes_by_metabolite(**params, conn=conn).get("results", [])

    builder = TOOL_BUILDERS[tool]
    limit = params.get("limit")
    # Strip tool-level params that aren't accepted by query builders
    builder_params = {k: v for k, v in params.items() if k not in ("limit",)}
    cypher, query_params = builder(**builder_params)
    results = conn.execute_query(cypher, **query_params)
    # Apply limit at the test level (mirrors MCP layer behavior)
    if limit is not None:
        results = results[:limit]

    # gene_details returns g{.*} AS gene — unwrap for flat column checks
    if tool == "gene_details" and results and "gene" in results[0]:
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
