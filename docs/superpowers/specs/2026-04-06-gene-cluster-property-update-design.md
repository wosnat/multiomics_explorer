# GeneCluster Property Update — Design Spec

**Date:** 2026-04-06
**Trigger:** KG rebuild changed GeneCluster node properties and ClusteringAnalysis.cluster_type values.

---

## What Changed in the KG

### GeneCluster properties

| Old property | New property | Notes |
|---|---|---|
| `behavioral_description` | `expression_dynamics` | Short label (e.g. "periodic in L:D only") |
| *(none)* | `temporal_pattern` | New long-form explanation (e.g. "Genes show 24-h periodicity in axenic cultures...") |
| `peak_time_hours` | *(removed)* | No replacement |
| `period_hours` | *(removed)* | No replacement |

Properties unchanged: `id`, `name`, `organism_name`, `member_count`, `functional_description`, `preferred_id`.

### ClusteringAnalysis.cluster_type values

| Old (7 values) | New (4 values) |
|---|---|
| `diel_cycling`, `diel_expression_pattern`, `periodicity_classification` | `diel` |
| `expression_classification`, `expression_level`, `expression_pattern` | `classification` |
| `response_pattern` | `condition_comparison` |
| *(none)* | `time_course` |

---

## Impact by Layer

### Layer 1 — `kg/constants.py`

Update `VALID_CLUSTER_TYPES`: replace 7 old values with 4 new values (`classification`, `condition_comparison`, `diel`, `time_course`).

### Layer 2 — `kg/queries_lib.py`

Three query builder functions reference removed GeneCluster properties in their Cypher RETURN clauses:

**`build_list_clustering_analyses`** (~line 2940):
- Inline cluster map builds `behavioral_description: gc.behavioral_description, peak_time_hours: gc.peak_time_hours, period_hours: gc.period_hours`
- Replace with: `expression_dynamics: gc.expression_dynamics, temporal_pattern: gc.temporal_pattern`
- Update docstring (verbose fields list)

**`build_gene_clusters_by_gene`** (~line 3133):
- Verbose RETURN: `gc.behavioral_description AS cluster_behavioral_description`, `gc.peak_time_hours AS peak_time_hours`, `gc.period_hours AS period_hours`
- Replace with: `gc.expression_dynamics AS cluster_expression_dynamics`, `gc.temporal_pattern AS cluster_temporal_pattern`
- Update docstring

**`build_genes_in_cluster`** (~line 3290):
- Verbose RETURN: `gc.behavioral_description AS cluster_behavioral_description`
- Replace with: `gc.expression_dynamics AS cluster_expression_dynamics`, `gc.temporal_pattern AS cluster_temporal_pattern`
- Update docstring

### Layer 3 — `api/functions.py`

Docstrings only (these functions pass through query builder output). Update verbose field lists in:
- `list_clustering_analyses` (~line 2265)
- `gene_clusters_by_gene` (~line 2265)
- `genes_in_cluster` (~line 2366)

### Layer 4 — `mcp_server/tools.py`

**Output model changes in 3 tools:**

`list_clustering_analyses`:
- `InlineCluster` model (~line 2572-2578): rename `behavioral_description` → `expression_dynamics`, add `temporal_pattern`, drop `peak_time_hours`, `period_hours`
- Verbose description (~line 2684): update field list

`gene_clusters_by_gene`:
- `GeneClusterResult` model (~line 2785-2789): rename `cluster_behavioral_description` → `cluster_expression_dynamics`, add `cluster_temporal_pattern`, drop `peak_time_hours`, `period_hours`
- Verbose description (~line 2862): update field list

`genes_in_cluster`:
- `GenesInClusterResult` model (~line 2953): rename `cluster_behavioral_description` → `cluster_expression_dynamics`, add `cluster_temporal_pattern`
- Verbose description (~line 3018): update field list

**Example value updates (e.g. strings):**
- `list_organisms` (~line 117): `cluster_types` example uses old values
- `list_publications` (~line 1003): same
- `list_experiments` (~line 1156): same
- Various `ClusterTypeBreakdown` models (~lines 129, 1027, 1195): example uses `'response_pattern'`

**Filter descriptions:** Auto-generated from `VALID_CLUSTER_TYPES` — will update when constants change (no manual edit needed).

### Tests

**Unit tests:**
- `test_query_builders.py`: assertions on `behavioral_description`, `peak_time_hours`, `period_hours` in verbose Cypher output (~lines 2840, 2987-2991, 3085-3092)
- `test_api_functions.py`: fixture data with old `cluster_types` values (`response_pattern`, `diel_cycling`) (~lines 766, 808-809, 1474, 1559, 1611, 1638, 1819)
- `test_tool_wrappers.py` / `test_tool_correctness.py`: likely reference old field names (check during implementation)
- `test_frames.py`: fixture data with `behavioral_description`, `peak_time_hours`, `period_hours` (~lines 469-471, 527-532)

**Integration tests:**
- `test_api_contract.py`: references `cluster_behavioral_description` (~lines 891, 955)
- `test_cyver_queries.py`: references `peak_time_hours`, `period_hours` in allowed-null list (~line 129)

**Regression fixtures (.yml):** All files under `tests/regression/` containing old cluster_type values need regeneration against live KG.

### Docs / Skills / YAML Inputs

Skill reference docs (`skills/multiomics-kg-guide/references/tools/*.md`) are **auto-generated** from YAML inputs + Pydantic models via `scripts/build_about_content.py`. Do not edit them manually.

**Update YAML input files first (human-authored content):**
- `inputs/tools/gene_clusters_by_gene.yaml`: example call (`cluster_type="stress_response"` → valid value), verbose_fields list (rename `cluster_behavioral_description` → `cluster_expression_dynamics` + add `cluster_temporal_pattern`, drop `peak_time_hours`/`period_hours`)
- `inputs/tools/genes_in_cluster.yaml`: verbose_fields list (rename `cluster_behavioral_description` → `cluster_expression_dynamics` + add `cluster_temporal_pattern`)
- `inputs/tools/list_clustering_analyses.yaml`: verbose_fields list (rename `clusters[].behavioral_description` → `clusters[].expression_dynamics` + add `clusters[].temporal_pattern`, drop `clusters[].peak_time_hours`/`clusters[].period_hours`)
- `inputs/tools/list_organisms.yaml`: example output values (old cluster_type examples)
- `inputs/tools/list_publications.yaml`: example output values (old cluster_type examples)
- `inputs/tools/list_experiments.yaml`: example output values (old cluster_type examples)
- `inputs/tools/gene_overview.yaml`: example output values (if referencing old cluster_types)

**Then regenerate skill reference docs:**
```bash
uv run python scripts/build_about_content.py
```

This regenerates all `.md` files from updated YAML inputs + updated Pydantic models (tools.py changes).

**Analysis utilities:**
- `analysis/frames.py` (~line 182): column name `behavioral_description` in cluster column list → `expression_dynamics` + add `temporal_pattern`, drop `peak_time_hours`/`period_hours`
- Skill doc `analysis/to_dataframe.md`: references old column names — will need manual update (not auto-generated)

### Out of Scope

- Historical docs/specs/plans (reflect past state, leave as-is)
- The drift test plan file (already stale from prior KG rebuild)

---

## Field Name Mapping Summary

For quick reference during implementation:

| Context | Old name | New name |
|---|---|---|
| GeneCluster property | `behavioral_description` | `expression_dynamics` |
| GeneCluster property | *(none)* | `temporal_pattern` (new) |
| GeneCluster property | `peak_time_hours` | *(drop)* |
| GeneCluster property | `period_hours` | *(drop)* |
| Inline cluster map key | `behavioral_description` | `expression_dynamics` |
| Inline cluster map key | *(none)* | `temporal_pattern` (new) |
| Inline cluster map key | `peak_time_hours` | *(drop)* |
| Inline cluster map key | `period_hours` | *(drop)* |
| Tool output field | `cluster_behavioral_description` | `cluster_expression_dynamics` |
| Tool output field | *(none)* | `cluster_temporal_pattern` (new) |
| Tool output field | `peak_time_hours` | *(drop)* |
| Tool output field | `period_hours` | *(drop)* |
| Constants | `VALID_CLUSTER_TYPES` 7 values | 4 values: `classification`, `condition_comparison`, `diel`, `time_course` |
