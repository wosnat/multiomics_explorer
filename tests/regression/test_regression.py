"""Regression tests: golden-file comparison for KG query results.

Detects ANY change in query output after KG rebuilds or code changes.
Uses pytest-regressions to save full results as YAML baselines.

Usage:
    pytest tests/regression/ -v                # compare against baselines
    pytest tests/regression/ --force-regen     # update baselines after intentional changes
"""

from pathlib import Path

import pytest
import yaml

from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_search_genes,
    build_resolve_gene,
    build_get_gene_details_main,
    build_get_homologs,
    build_homolog_expression,
    build_query_expression,
)

# ---------------------------------------------------------------------------
# Load cases (shared with evals)
# ---------------------------------------------------------------------------

CASES_PATH = Path(__file__).parent.parent / "evals" / "cases.yaml"
CASES = yaml.safe_load(CASES_PATH.read_text())
CASE_IDS = [c["id"] for c in CASES]

TOOL_BUILDERS = {
    "resolve_gene": build_resolve_gene,
    "search_genes": build_search_genes,
    "get_gene_details": build_get_gene_details_main,
    "query_expression": build_query_expression,
    "compare_conditions": build_compare_conditions,
    "get_homologs": build_get_homologs,
}


# ---------------------------------------------------------------------------
# Normalization for stable golden files
# ---------------------------------------------------------------------------


def _normalize(results: list[dict]) -> list[dict]:
    """Prepare query results for deterministic golden-file comparison.

    - Sort rows by locus_tag or gene key for stable ordering
    - Round floats to 4 decimal places to avoid precision noise
    - Sort dict keys and list values for consistent YAML output
    """
    # Determine sort key
    if results and "locus_tag" in results[0]:
        sort_key = "locus_tag"
    elif results and "gene" in results[0]:
        sort_key = "gene"
    elif results and "cnt" in results[0]:
        sort_key = "cnt"
    else:
        sort_key = None

    if sort_key:
        results = sorted(results, key=lambda r: str(r.get(sort_key, "")))

    cleaned = []
    for row in results:
        cleaned_row = {}
        for k in sorted(row.keys()):
            v = row[k]
            if isinstance(v, float):
                cleaned_row[k] = round(v, 4)
            elif isinstance(v, list):
                cleaned_row[k] = sorted(str(x) for x in v) if v else []
            else:
                cleaned_row[k] = v
        cleaned.append(cleaned_row)

    return cleaned


# ---------------------------------------------------------------------------
# Parameterized regression test
# ---------------------------------------------------------------------------


@pytest.mark.kg
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_regression(conn, case, data_regression):
    tool = case["tool"]
    params = case.get("params", {})

    if tool == "raw_cypher":
        results = conn.execute_query(params["query"])
    elif tool == "get_homologs_with_expression":
        cypher, query_params = build_get_homologs(gene_id=params["gene_id"])
        homologs = conn.execute_query(cypher, **query_params)
        if not homologs:
            results = []
        else:
            all_ids = [params["gene_id"]] + [h["locus_tag"] for h in homologs]
            cypher_expr, params_expr = build_homolog_expression(gene_ids=all_ids)
            results = conn.execute_query(cypher_expr, **params_expr)
    else:
        builder = TOOL_BUILDERS[tool]
        # Strip tool-level params that aren't accepted by query builders
        builder_params = {k: v for k, v in params.items() if k != "deduplicate"}
        cypher, query_params = builder(**builder_params)
        results = conn.execute_query(cypher, **query_params)

    normalized = _normalize(results)
    data_regression.check({
        "case_id": case["id"],
        "row_count": len(normalized),
        "rows": normalized,
    }, basename=case["id"])
