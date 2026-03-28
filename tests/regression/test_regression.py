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
    build_differential_expression_by_gene,
    build_gene_ontology_terms,
    build_gene_overview,
    build_gene_stub,
    build_genes_by_function,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_summary,
    build_genes_by_ontology,
    build_get_gene_details,
    build_gene_homologs,
    build_list_experiments,
    build_list_experiments_summary,
    build_list_gene_categories,
    build_list_organisms,
    build_list_publications,
    build_resolve_gene,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
    build_search_ontology,
    build_differential_expression_by_ortholog_results,
)

# ---------------------------------------------------------------------------
# Load cases (shared with evals)
# ---------------------------------------------------------------------------

CASES_PATH = Path(__file__).parent.parent / "evals" / "cases.yaml"
CASES = yaml.safe_load(CASES_PATH.read_text())
CASE_IDS = [c["id"] for c in CASES]

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
    "list_publications": build_list_publications,
    "list_experiments": build_list_experiments,
    "list_experiments_summary": build_list_experiments_summary,
    "differential_expression_by_gene": build_differential_expression_by_gene,
    "search_homolog_groups": build_search_homolog_groups,
    "search_homolog_groups_summary": build_search_homolog_groups_summary,
    "genes_by_homolog_group": build_genes_by_homolog_group,
    "genes_by_homolog_group_summary": build_genes_by_homolog_group_summary,
    "differential_expression_by_ortholog": build_differential_expression_by_ortholog_results,
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
    elif results and "organism_name" in results[0]:
        sort_key = "organism_name"
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
        results = conn.execute_query(cat_cypher, **cat_params)
    elif tool == "gene_homologs_with_members":
        cypher, params_b = build_gene_homologs(locus_tags=params["locus_tags"])
        results = conn.execute_query(cypher, **params_b)
    else:
        builder = TOOL_BUILDERS[tool]
        # Strip tool-level params that aren't accepted by query builders
        builder_params = {k: v for k, v in params.items() if k not in ("deduplicate", "limit")}
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
