"""Regression tests: golden-file comparison for KG query results.

Detects ANY change in query output after KG rebuilds or code changes.
Uses pytest-regressions to save full results as YAML baselines.

Usage:
    pytest tests/regression/ -v                # compare against baselines
    pytest tests/regression/ --force-regen     # update baselines after intentional changes
"""

from functools import partial
from pathlib import Path

import pytest
import yaml

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
    build_search_ontology,
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
    "gene_overview": build_gene_overview,
    "get_gene_details": build_get_gene_details,
    "query_expression": build_query_expression,
    "compare_conditions": build_compare_conditions,
    "get_homologs": build_get_homologs_groups,
    "list_organisms": build_list_organisms,
    "search_ontology": build_search_ontology,
    "genes_by_ontology": build_genes_by_ontology,
    "gene_ontology_terms": build_gene_ontology_terms,
    # Per-ontology partial entries for regression snapshots
    "search_ontology_go_bp": partial(build_search_ontology, ontology="go_bp"),
    "search_ontology_kegg": partial(build_search_ontology, ontology="kegg"),
    "search_ontology_ec": partial(build_search_ontology, ontology="ec"),
    "search_ontology_cog_category": partial(build_search_ontology, ontology="cog_category"),
    "search_ontology_cyanorak_role": partial(build_search_ontology, ontology="cyanorak_role"),
    "search_ontology_tigr_role": partial(build_search_ontology, ontology="tigr_role"),
    "genes_by_ontology_go_bp": partial(build_genes_by_ontology, ontology="go_bp"),
    "genes_by_ontology_kegg": partial(build_genes_by_ontology, ontology="kegg"),
    "genes_by_ontology_ec": partial(build_genes_by_ontology, ontology="ec"),
    "genes_by_ontology_cog_category": partial(build_genes_by_ontology, ontology="cog_category"),
    "genes_by_ontology_cyanorak_role": partial(build_genes_by_ontology, ontology="cyanorak_role"),
    "genes_by_ontology_tigr_role": partial(build_genes_by_ontology, ontology="tigr_role"),
    "gene_ontology_terms_go_bp": partial(build_gene_ontology_terms, ontology="go_bp"),
    "gene_ontology_terms_kegg": partial(build_gene_ontology_terms, ontology="kegg"),
    "gene_ontology_terms_ec": partial(build_gene_ontology_terms, ontology="ec"),
    "gene_ontology_terms_cog_category": partial(build_gene_ontology_terms, ontology="cog_category"),
    "gene_ontology_terms_cyanorak_role": partial(build_gene_ontology_terms, ontology="cyanorak_role"),
    "gene_ontology_terms_tigr_role": partial(build_gene_ontology_terms, ontology="tigr_role"),
    "search_ontology_pfam": partial(build_search_ontology, ontology="pfam"),
    "genes_by_ontology_pfam": partial(build_genes_by_ontology, ontology="pfam"),
    "gene_ontology_terms_pfam": partial(build_gene_ontology_terms, ontology="pfam"),
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
    elif results and "category" in results[0]:
        sort_key = "category"
    elif results and "id" in results[0]:
        sort_key = "id"
    elif results and "name" in results[0]:
        sort_key = "name"
    elif results and "condition_type" in results[0]:
        sort_key = "condition_type"
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
    elif tool == "list_filter_values":
        cat_cypher, cat_params = build_list_gene_categories()
        categories = conn.execute_query(cat_cypher, **cat_params)
        cond_cypher, cond_params = build_list_condition_types()
        condition_types = conn.execute_query(cond_cypher, **cond_params)
        results = categories + condition_types
    elif tool == "get_homologs_with_members":
        cypher_groups, params_groups = build_get_homologs_groups(gene_id=params["gene_id"])
        results = conn.execute_query(cypher_groups, **params_groups)
    else:
        builder = TOOL_BUILDERS[tool]
        # Strip tool-level params that aren't accepted by query builders
        builder_params = {k: v for k, v in params.items() if k != "deduplicate"}
        # gene_overview: map gene_ids -> locus_tags for the query builder
        if tool == "gene_overview" and "gene_ids" in builder_params:
            builder_params["locus_tags"] = builder_params.pop("gene_ids")
        cypher, query_params = builder(**builder_params)
        results = conn.execute_query(cypher, **query_params)
        # get_gene_details returns g{.*} AS gene — unwrap for flat comparison
        if tool == "get_gene_details" and results and "gene" in results[0]:
            results = [r["gene"] for r in results if r.get("gene") is not None]

    normalized = _normalize(results)
    data_regression.check({
        "case_id": case["id"],
        "row_count": len(normalized),
        "rows": normalized,
    }, basename=case["id"])
