# KG Constants Drift Tests

**Date:** 2026-04-06
**Status:** Approved

## Problem

Hardcoded values in Pydantic models and constants can drift from actual KG content when new papers/organisms are added. One drift already exists: `VALID_TAXONOMIC_LEVELS` has `Gammaproteobacteria` but KG now has `Proteobacteria`. Tool descriptions for `cluster_type` and `omics_type` are also stale.

## Solution

Integration tests (`@pytest.mark.kg`) that query the live KG and assert exact match against hardcoded constants. New constants for `cluster_type` and `omics_type` to make them testable and keep tool descriptions in sync.

## Scope

### Constants to test (7 total)

| # | Constant | Location | KG Query |
|---|----------|----------|----------|
| 1 | `VALID_OG_SOURCES` | `kg/constants.py` | `DISTINCT og.source` from OrthologGroup |
| 2 | `VALID_TAXONOMIC_LEVELS` | `kg/constants.py` | `DISTINCT og.taxonomic_level` from OrthologGroup |
| 3 | `MAX_SPECIFICITY_RANK` | `kg/constants.py` | `MAX(og.specificity_rank)` from OrthologGroup |
| 4 | `ONTOLOGY_CONFIG` | `kg/queries_lib.py` | Per entry: node label exists, gene_rel exists, hierarchy_rels exist, fulltext index queryable |
| 5 | `expression_status` Literal | `mcp_server/tools.py` | `DISTINCT r.expression_status` from Changes_expression_of |
| 6 | `VALID_CLUSTER_TYPES` | `kg/constants.py` (new) | `DISTINCT ca.cluster_type` from ClusteringAnalysis |
| 7 | `VALID_OMICS_TYPES` | `kg/constants.py` (new) | `DISTINCT e.omics_type` from Experiment |

### Fixes included

1. **`VALID_TAXONOMIC_LEVELS`**: replace `Gammaproteobacteria` with `Proteobacteria`
2. **New constants**: `VALID_CLUSTER_TYPES` and `VALID_OMICS_TYPES` in `kg/constants.py`
3. **Tool descriptions**: update `cluster_type` and `omics_type` descriptions in `tools.py` to reference the new constants (f-string or `.join()`) so they stay in sync

### Test file

`tests/integration/test_kg_constants_drift.py`

- `@pytest.mark.kg` — runs with `pytest -m kg`
- Uses existing `kg_connection` fixture
- One test function per constant (clear names like `test_valid_og_sources_match_kg`)
- Failures show set diff (`expected - actual`, `actual - expected`)

### ONTOLOGY_CONFIG validation detail

For each key in `ONTOLOGY_CONFIG`, verify:
- `label`: node with that label exists in KG
- `gene_rel`: relationship type exists in KG
- `hierarchy_rels`: each relationship type exists in KG (skip if empty list)
- `fulltext_index`: a simple fulltext query succeeds without error
- `parent_label` (if present): node with that label exists
- `parent_fulltext_index` (if present): queryable

### expression_status validation

Extract the 3 values from the `DifferentialExpressionResult.expression_status` Literal type annotation and compare against `DISTINCT r.expression_status` from KG edges.

## Out of scope

- Detecting new ontology types the KG might add (completeness check) — caught during KG rebuild reviews
- Dynamic values like `treatment_type`, `background_factors` — discovered at query time via tools
- `gene_category` — already dynamic via `list_filter_values`
- `direction` (`up`/`down`), `group_by` — semantic/logic-driven, won't change
