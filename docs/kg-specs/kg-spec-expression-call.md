# KG change spec: expression_status on Changes_expression_of edges

## Summary

Add `expression_status` as a derived property on `Changes_expression_of` edges.
Split all precomputed significant counts into directional `significant_up_count` /
`significant_down_count` on Experiment and Gene nodes.

**Status: implemented in KG repo — rebuild in progress (2026-03-24).**

See `multiomics_biocypher_kg/docs/kg-changes/expression-status.md` for the authoritative spec.

## New Edge Property

| Edge | Property | Type | Values |
|---|---|---|---|
| `Changes_expression_of` | `expression_status` | str | `"significant_up"`, `"significant_down"`, `"not_significant"` |

Derived from `significant` + `expression_direction` at build time. Source properties retained.

## Property Renames — Experiment Nodes

| Before | After |
|---|---|
| `significant_count` | `significant_up_count` + `significant_down_count` |
| `time_point_significants` | `time_point_significant_up` + `time_point_significant_down` (parallel arrays) |

## Property Renames — Gene Nodes

| Before | After |
|---|---|
| `significant_expression_count` | `significant_up_count` + `significant_down_count` |

## MCP Code Impact (fix after rebuild)

| File | Location | Old reference | New reference |
|---|---|---|---|
| `kg/queries_lib.py` | `build_list_experiments_summary` (line ~701) | `significant_count` | `significant_up_count`, `significant_down_count` |
| `kg/queries_lib.py` | `build_list_experiments` (line ~745) | `e.significant_count`, `e.time_point_significants` | `e.significant_up_count`, `e.significant_down_count`, `e.time_point_significant_up`, `e.time_point_significant_down` |
| `api/functions.py` | `list_experiments` (line ~563, ~667) | `significant_count`, `time_point_significants` | updated names |
| `mcp_server/tools.py` | `ListExperimentsResult` (line ~1032) | `significant_count` | `significant_up_count`, `significant_down_count` |
| `kg/queries_lib.py` | `build_gene_overview` (line ~236, ~282) | `significant_expression_count` | `significant_up_count`, `significant_down_count` |
| `api/functions.py` | `gene_overview` (line ~237) | `significant_expression_count` | updated |
| `mcp_server/tools.py` | `GeneOverviewResult` (line ~373) | `significant_expression_count` | `significant_up_count`, `significant_down_count` |
