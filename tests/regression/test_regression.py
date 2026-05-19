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

import multiomics_explorer.api.functions as api
from multiomics_explorer.kg.queries_lib import (
    build_differential_expression_by_gene,
    build_differential_expression_by_ortholog_results,
    build_gene_derived_metrics,
    build_gene_derived_metrics_summary,
    build_gene_details,
    build_genes_by_boolean_metric,
    build_genes_by_boolean_metric_summary,
    build_genes_by_categorical_metric,
    build_genes_by_categorical_metric_summary,
    build_genes_by_numeric_metric,
    build_gene_homologs,
    build_gene_ontology_terms,
    build_gene_overview,
    build_gene_response_profile,
    build_genes_by_function,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_summary,
    build_list_derived_metrics,
    build_list_derived_metrics_summary,
    build_list_experiments,
    build_list_experiments_summary,
    build_list_compartments,
    build_list_gene_categories,
    build_genes_by_metabolite_metabolism,
    build_list_metabolite_assays,
    build_list_metabolites,
    build_metabolites_by_gene_metabolism,
    build_metabolites_by_quantifies_assay,
    build_metabolites_by_quantifies_assay_summary,
    build_metabolites_by_flags_assay,
    build_metabolites_by_flags_assay_summary,
    build_assays_by_metabolite,
    build_assays_by_metabolite_summary,
    build_list_metric_types,
    build_list_organisms,
    build_list_publications,
    build_list_value_kinds,
    build_resolve_gene,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
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
    "genes_by_function": build_genes_by_function,
    "gene_overview": build_gene_overview,
    "gene_details": build_gene_details,
    "gene_homologs": build_gene_homologs,
    "list_organisms": build_list_organisms,
    "search_ontology": build_search_ontology,
    # genes_by_ontology: dispatched via api (L2) — returns envelope, not flat rows
    "genes_by_ontology": None,
    "gene_ontology_terms": build_gene_ontology_terms,
    "list_publications": build_list_publications,
    "list_metabolites": build_list_metabolites,
    "list_metabolite_assays": build_list_metabolite_assays,
    "genes_by_metabolite": build_genes_by_metabolite_metabolism,
    "metabolites_by_gene": build_metabolites_by_gene_metabolism,
    "metabolites_by_quantifies_assay": build_metabolites_by_quantifies_assay,
    "metabolites_by_quantifies_assay_summary": build_metabolites_by_quantifies_assay_summary,
    "metabolites_by_flags_assay": build_metabolites_by_flags_assay,
    "metabolites_by_flags_assay_summary": build_metabolites_by_flags_assay_summary,
    "assays_by_metabolite": build_assays_by_metabolite,
    "assays_by_metabolite_summary": build_assays_by_metabolite_summary,
    "list_derived_metrics": build_list_derived_metrics,
    "list_derived_metrics_summary": build_list_derived_metrics_summary,
    "gene_derived_metrics": build_gene_derived_metrics,
    "gene_derived_metrics_summary": build_gene_derived_metrics_summary,
    "genes_by_numeric_metric": build_genes_by_numeric_metric,
    "genes_by_boolean_metric": build_genes_by_boolean_metric,
    "genes_by_boolean_metric_summary": build_genes_by_boolean_metric_summary,
    "genes_by_categorical_metric": build_genes_by_categorical_metric,
    "genes_by_categorical_metric_summary": build_genes_by_categorical_metric_summary,
    "list_experiments": build_list_experiments,
    "list_experiments_summary": build_list_experiments_summary,
    "differential_expression_by_gene": build_differential_expression_by_gene,
    "search_homolog_groups": build_search_homolog_groups,
    "search_homolog_groups_summary": build_search_homolog_groups_summary,
    "genes_by_homolog_group": build_genes_by_homolog_group,
    "genes_by_homolog_group_summary": build_genes_by_homolog_group_summary,
    "differential_expression_by_ortholog": build_differential_expression_by_ortholog_results,
    "gene_response_profile": build_gene_response_profile,
    # ontology_landscape: dispatched via api (L2), not a query builder
    "ontology_landscape": None,
    # pathway_enrichment: dispatched via api (L2), not a query builder
    "pathway_enrichment": None,
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
        filter_type = params.get("filter_type", "gene_category")
        _filter_builders = {
            "gene_category": build_list_gene_categories,
            "metric_type": build_list_metric_types,
            "value_kind": build_list_value_kinds,
            "compartment": build_list_compartments,
        }
        fb = _filter_builders.get(filter_type, build_list_gene_categories)
        cat_cypher, cat_params = fb()
        results = conn.execute_query(cat_cypher, **cat_params)
    elif tool == "gene_homologs_with_members":
        cypher, params_b = build_gene_homologs(locus_tags=params["locus_tags"])
        results = conn.execute_query(cypher, **params_b)
    elif tool == "ontology_landscape":
        data = api.ontology_landscape(**params, conn=conn)
        results = data["results"]
    elif tool == "genes_by_ontology":
        # Capture full envelope (top-level fields + results rows) — the new
        # response shape is rich and changes here should surface cleanly.
        data = api.genes_by_ontology(**params, conn=conn)
        normalized_rows = _normalize(data.get("results", []))
        envelope = {k: v for k, v in data.items() if k != "results"}
        envelope["results"] = normalized_rows
        envelope["row_count"] = len(normalized_rows)
        data_regression.check(
            {"case_id": case["id"], **envelope},
            basename=case["id"],
        )
        return
    elif tool == "pathway_enrichment":
        # Capture full envelope — shape changes (new summary fields, etc.)
        # should surface cleanly in the golden file diff.
        data = api.pathway_enrichment(**params, conn=conn).to_envelope()
        normalized_rows = _normalize(data.get("results", []))
        envelope = {k: v for k, v in data.items() if k != "results"}
        envelope["results"] = normalized_rows
        envelope["row_count"] = len(normalized_rows)
        data_regression.check(
            {"case_id": case["id"], **envelope},
            basename=case["id"],
        )
        return
    elif tool == "genes_by_numeric_metric":
        # Dispatch via api (L2) — builder takes resolved derived_metric_ids
        # only; the api handles metric_types → ID resolution + gate
        # validation. Capture full envelope so shape changes surface cleanly.
        data = api.genes_by_numeric_metric(**params, conn=conn)
        normalized_rows = _normalize(data.get("results", []))
        envelope = {k: v for k, v in data.items() if k != "results"}
        envelope["results"] = normalized_rows
        envelope["row_count"] = len(normalized_rows)
        data_regression.check(
            {"case_id": case["id"], **envelope},
            basename=case["id"],
        )
        return
    elif tool == "genes_by_boolean_metric":
        # Dispatch via api (L2) — builder takes resolved derived_metric_ids
        # only; the api handles metric_types → ID resolution. Capture full
        # envelope so shape changes surface cleanly.
        data = api.genes_by_boolean_metric(**params, conn=conn)
        normalized_rows = _normalize(data.get("results", []))
        envelope = {k: v for k, v in data.items() if k != "results"}
        envelope["results"] = normalized_rows
        envelope["row_count"] = len(normalized_rows)
        data_regression.check(
            {"case_id": case["id"], **envelope},
            basename=case["id"],
        )
        return
    elif tool == "genes_by_categorical_metric":
        # Dispatch via api (L2) — same as boolean. The api handles
        # metric_types → ID resolution + categories ⊆ allowed_categories
        # validation.
        data = api.genes_by_categorical_metric(**params, conn=conn)
        normalized_rows = _normalize(data.get("results", []))
        envelope = {k: v for k, v in data.items() if k != "results"}
        envelope["results"] = normalized_rows
        envelope["row_count"] = len(normalized_rows)
        data_regression.check(
            {"case_id": case["id"], **envelope},
            basename=case["id"],
        )
        return
    elif tool == "list_metabolites":
        # Dispatch via api (L2) — organism_names lowercasing + summary/detail
        # split + not_found computation live above the builder.
        data = api.list_metabolites(**params, conn=conn)
        normalized_rows = _normalize(data.get("results", []))
        envelope = {k: v for k, v in data.items() if k != "results"}
        envelope["results"] = normalized_rows
        envelope["row_count"] = len(normalized_rows)
        data_regression.check(
            {"case_id": case["id"], **envelope},
            basename=case["id"],
        )
        return
    elif tool == "genes_by_metabolite":
        # Dispatch via api (L2) — two-arm dispatch + global sort + slice +
        # not_found / not_matched + auto-warning live above the builders.
        data = api.genes_by_metabolite(**params, conn=conn)
        normalized_rows = _normalize(data.get("results", []))
        envelope = {k: v for k, v in data.items() if k != "results"}
        envelope["results"] = normalized_rows
        envelope["row_count"] = len(normalized_rows)
        data_regression.check(
            {"case_id": case["id"], **envelope},
            basename=case["id"],
        )
        return
    else:
        builder = TOOL_BUILDERS[tool]
        # Strip tool-level params that aren't accepted by query builders
        builder_params = {k: v for k, v in params.items() if k not in ("deduplicate", "limit")}
        cypher, query_params = builder(**builder_params)
        results = conn.execute_query(cypher, **query_params)
        # gene_details returns g{.*} AS gene — unwrap for flat comparison
        if tool == "gene_details" and results and "gene" in results[0]:
            results = [r["gene"] for r in results if r.get("gene") is not None]

    normalized = _normalize(results)
    data_regression.check({
        "case_id": case["id"],
        "row_count": len(normalized),
        "rows": normalized,
    }, basename=case["id"])
