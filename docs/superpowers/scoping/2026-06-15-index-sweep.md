# `[0]`-index call-site sweep (Task 0.1)

Working notes for the corner-case verification plan. Goal: inventory every
`conn.execute_query(cypher, **params)[0]` site and classify each as **SAFE**
(the RETURN aggregates → always exactly one row, even on empty input) or
**RISK** (per-row projection → zero rows on no-match → `IndexError`).

Investigation only — no code changed.

## Method

```bash
grep -rn "execute_query(.*)\[0\]\|)\[0\]\[" \
  multiomics_explorer/api/functions.py \
  multiomics_explorer/mcp_server/tools.py \
  multiomics_explorer/analysis/*.py
```

Supplemented with:

- `grep -rn "^\s*)\[0\]"` to catch multi-line call sites where `)[0]` lands on
  a line after `execute_query(` (found sites at functions.py:2491 and :2607).
- `grep -n "execute_query"` over tools.py and analysis/*.py — **zero hits**:
  no `execute_query` call exists outside `api/functions.py`. The MCP layer and
  the analysis layer reach the graph only through the public api functions, so
  every `[0]` crash site lives in `functions.py`.
- For each site, traced the builder named on the preceding `build_*(...)` line
  into `kg/queries_lib.py` and read its terminal `RETURN`.

## Key finding (counts)

- **Total `execute_query(...)[0]` sites found: 31** (all in `api/functions.py`).
- **SAFE: 31**
- **RISK: 0**

Every single `[0]` site is fed by a query builder whose terminal `RETURN`
aggregates with no grouping key (`count(...)`, `collect(...)`,
`apoc.coll.frequencies(...)`, `apoc.coll.flatten(...)`, `size(...)`,
`percentileCont(...)`), and in every multi-key case the builder first funnels
through an intermediate `WITH collect(...) AS ...` / `WITH count(...) AS ...`
that guarantees one row before any literal-grouping `RETURN`. Cypher
aggregations return exactly one row even when the MATCH found nothing, so `[0]`
cannot raise.

### Note on the known DE bug class

The known crash class ("entity with no `Changes_expression_of` edges →
`IndexError`") does **not** appear at any `[0]` site routed through these
builders. The DE summary builder
`build_differential_expression_by_gene_summary_global`
(`queries_lib.py:3485`, consumed at `functions.py:2407`) matches
`(e:Experiment)-[r:Changes_expression_of]->(g:Gene)` and then does
`RETURN count(*) AS total_matching, ...` — a bare aggregation, so a gene with
zero expression edges still yields one row (`total_matching = 0`). SAFE.

Likewise the `_summary_diagnostics` builder (`3590`) carries an explicit
in-code comment (lines 3615-3617) documenting that it deliberately routes
through `WITH collect(...) AS top_categories` precisely to avoid the
literal-grouping-key zero-row trap. So the DE family is hardened at the
builder layer.

**Implication for later tasks:** if a real DE-empty-entity `IndexError` exists
in this repo, it is **not** at an `execute_query(...)[0]` site — it would be a
different shape (e.g. `rows[0]` after a separate fetch, `.iloc[0]` on an empty
DataFrame, dict/list indexing on an api return value, or a `[0]` inside a
list/dict comprehension). Those are out of scope for this `[0]`-on-execute_query
sweep but worth flagging for the next task. Candidates seen while sweeping
(NOT execute_query sites, classified separately, all already guarded or
operating on aggregated/guaranteed-nonempty data):

- `analysis/enrichment.py:809` — `analysis_meta_result["results"][0] if ... else {}` — **guarded**.
- `analysis/enrichment.py:1189,1237` — `rows.iloc[0].to_dict()` on a pandas DataFrame (not execute_query) — out of scope here.
- `analysis/frames.py:66,256` — `rows_list[0]` / `rows[0]` guarded by `if rows`/length checks — out of scope here.

## Site-by-site classification

All sites are in `multiomics_explorer/api/functions.py`. "Builder" = the
`build_*` function in `kg/queries_lib.py` whose Cypher is passed to the call.

| file:line | function (tool) | builder | classification | reasoning (what the RETURN does) | degenerate trigger (RISK only) |
|---|---|---|---|---|---|
| functions.py:320 | `genes_by_function` | `build_genes_by_function_summary` (qlib:349) | SAFE | `WITH count(g)...` then `RETURN total_*, apoc.coll.frequencies(...)` — bare aggregation | — |
| functions.py:409 | `gene_overview` | `build_gene_overview_summary` (qlib:445) | SAFE | `WITH collect(...)` then `RETURN total_matching, apoc.coll.frequencies(...)` | — |
| functions.py:559 | `discussed_by_publication` | `build_discussed_by_publication_summary` (qlib:1215) | SAFE | correlated `CALL{}` + `WITH collect(...)`; `RETURN total_entries, apoc.coll.frequencies([...])` (docstring guarantees one row) | — |
| functions.py:639 | `gene_details` | `build_gene_details_summary` (qlib:624) | SAFE | `WITH collect(...) AS found, collect(...) AS not_found` then `RETURN size(found) AS total_matching, not_found` | — |
| functions.py:731 | `gene_homologs` | `build_gene_homologs_summary` (qlib:683) | SAFE | terminal `RETURN size(sources) AS total_matching, apoc.coll.frequencies(...)` over collected lists | — |
| functions.py:1069 | `list_publications` | `build_list_publications_summary` (qlib:1014) | SAFE | both branches `WITH count(p)...` then `RETURN count(p2) AS total_entries, ..., apoc.coll.frequencies(...)`; empty-filter branch keeps a `MATCH` to force one row | — |
| functions.py:1240 | `list_experiments` | `build_list_experiments_summary` (qlib:2202) | SAFE | `RETURN {return_cols}` = all `apoc.coll.frequencies(...)` over collected lists | — |
| functions.py:1264 | `list_experiments` (total_entries) | `build_list_experiments_summary` (qlib:2202) | SAFE | same builder, no-filter call → still one aggregated row | — |
| functions.py:1455 | `search_ontology` | `build_search_ontology_summary` (qlib:2299) | SAFE | `WITH count(...) AS total_matching, ...` + `CALL{... count ...}` then scalar `RETURN` | — |
| functions.py:1464 | `search_ontology` (escaped retry) | `build_search_ontology_summary` (qlib:2299) | SAFE | same builder | — |
| functions.py:1582 | `search_homolog_groups` | `build_search_homolog_groups_summary` (qlib:3813) | SAFE | `WITH collect(...), count(DISTINCT og) AS total_matching` + `CALL{count}` then `RETURN ..., apoc.coll.frequencies(...)` | — |
| functions.py:1588 | `search_homolog_groups` (escaped retry) | `build_search_homolog_groups_summary` (qlib:3813) | SAFE | same builder | — |
| functions.py:1672 | `genes_by_homolog_group` | `build_genes_by_homolog_group_summary` (qlib:3957) | SAFE | `OPTIONAL MATCH` + `WITH collect(...)` then `RETURN total_matching, ..., apoc.coll.frequencies(...)` | — |
| functions.py:1698 | `genes_by_homolog_group` (diagnostics) | `build_genes_by_homolog_group_diagnostics` (qlib:4001) | SAFE | `WITH collect(CASE...)` then `RETURN [x IN nf_raw WHERE ...] AS not_found_organisms, ...` | — |
| functions.py:2253 | `_validate_organism_inputs` (organism) | `build_resolve_organism_for_organism` (qlib:3428) | SAFE | `RETURN collect(DISTINCT o.preferred_name) AS organisms` — bare collect | — |
| functions.py:2271 | `_validate_organism_inputs` (locus_tags) | `build_resolve_organism_for_locus_tags` (qlib:3450) | SAFE | `UNWIND` + `RETURN collect(DISTINCT g.organism_name) AS organisms` | — |
| functions.py:2285 | `_validate_organism_inputs` (experiment_ids) | `build_resolve_organism_for_experiments` (qlib:3465) | SAFE | `UNWIND` + `RETURN collect(DISTINCT e.organism_name) AS organisms` | — |
| functions.py:2407 | `differential_expression_by_gene` (global) | `build_differential_expression_by_gene_summary_global` (qlib:3485) | SAFE | `MATCH ...Changes_expression_of... RETURN count(*) AS total_matching, ..., apoc.coll.frequencies(...)` — bare aggregation off the DE edge; one row even with zero edges | — |
| functions.py:2471 | `differential_expression_by_gene` (diagnostics) | `build_differential_expression_by_gene_summary_diagnostics` (qlib:3590) | SAFE | both branches funnel through `WITH collect(...) AS top_categories` before `RETURN` (explicit anti-zero-row comment at qlib:3615-3617) | — |
| functions.py:2491 | `differential_expression_by_gene` (experiment diag) | `build_differential_expression_by_gene_experiment_diagnostics` (qlib:3684) | SAFE | `UNWIND` + `WITH collect(CASE...)` then `RETURN [x IN nf_raw WHERE ...] AS not_found_experiments, ...` | — |
| functions.py:2607 | `differential_expression_by_ortholog` (group check) | `build_differential_expression_by_ortholog_group_check` (qlib:4136) | SAFE | `UNWIND` + `WITH collect(CASE WHEN og IS NULL...)` then `RETURN [x IN nf_raw WHERE ...] AS not_found` | — |
| functions.py:2707 | `differential_expression_by_ortholog` (diag loop) | `build_differential_expression_by_ortholog_diagnostics` → `_build_de_by_ortholog_{organism,experiment}_diagnostics` (qlib:4422 / 4476) | SAFE | each sub-builder ends `WITH collect(CASE...)` then `RETURN [x IN nf_raw WHERE ...] AS ...`; loop only runs over builder-returned queries | — |
| functions.py:2819 | `gene_response_profile` (envelope) | `build_gene_response_profile_envelope` (qlib:4614) | SAFE | `WITH collect(g.locus_tag) AS found_genes` then `RETURN found_genes, has_expression, has_significant, group_totals` — all collected/aggregated | — |
| functions.py:2994 | `list_clustering_analyses` | `build_list_clustering_analyses_summary` (qlib:4853) | SAFE | `WITH collect(...), count(ca) AS total_matching` + `CALL{count}` then `RETURN ..., apoc.coll.frequencies(...)` | — |
| functions.py:3001 | `list_clustering_analyses` (escaped retry) | `build_list_clustering_analyses_summary` (qlib:4853) | SAFE | same builder | — |
| functions.py:3118 | `list_derived_metrics` | `build_list_derived_metrics_summary` (qlib:5715) | SAFE | `WITH collect(...), count(dm) AS total_matching` + `CALL{count}` then `RETURN ..., apoc.coll.frequencies(...)` | — |
| functions.py:3125 | `list_derived_metrics` (escaped retry) | `build_list_derived_metrics_summary` (qlib:5715) | SAFE | same builder | — |
| functions.py:3242 | `gene_clusters_by_gene` | `build_gene_clusters_by_gene_summary` (qlib:5058) | SAFE | `UNWIND` + `WITH collect(...)` then `RETURN total_matching, total_clusters, ..., apoc.coll.frequencies(...)` | — |
| functions.py:3345 | `gene_derived_metrics` | `build_gene_derived_metrics_summary` (qlib:5898) | SAFE | `UNWIND` + `WITH collect(...)` then `RETURN size(rows) AS total_matching, ..., apoc.coll.frequencies(...)` | — |
| functions.py:4269 | `genes_in_cluster` | `build_genes_in_cluster_summary` (qlib:5239) | SAFE | both modes `WITH collect(...)` then `RETURN total_matching, by_organism, ..., apoc.coll.frequencies(...)` | — |
| functions.py:4433 | `ontology_landscape` (gene count) | `build_ontology_organism_gene_count` (qlib:5605) | SAFE | `MATCH (g:Gene {organism_name:$org}) RETURN count(g) AS total_genes` — bare count; `[0]["total_genes"]` is 0 on unknown organism, never raises | — |
| functions.py:5084 | `list_metabolites` | `build_list_metabolites_summary` (qlib:1527) | SAFE | both branches `WITH count(m)...` then `RETURN total_entries, total_matching, apoc.coll.frequencies(...)`; empty-filter branch keeps a `MATCH` to force one row | — |

## Conclusion

The `[0]`-on-`execute_query` surface is fully hardened: 31/31 SAFE, because the
codebase consistently routes every single-row fetch through an aggregating
summary/diagnostic/envelope/check builder. No fix is required at any of these
sites. The DE-empty-entity crash class, if it exists in this repo, must be at a
non-`execute_query(...)[0]` indexing site (pandas `.iloc[0]`, post-fetch
`rows[0]`, or dict/list indexing on api-return structures) — flagged above for a
follow-up sweep, but out of scope for this task.

## Live-probe addendum (controller, 2026-06-15)

The static `[0]` sweep found **0 RISK sites**. To confirm the known
"`Changes_expression_of` index error when no experiments" is not lurking in a
different shape, the DE/enrichment family was probed live against the two
empty-expression fixtures — `Prochlorococcus MIT9515` (genome-only, 0
experiments) and `Prochlorococcus MIT0801` (6 experiments, METABOLOMICS-only,
0 `Changes_expression_of` edges) — at **both** the api layer and the MCP
wrapper (Pydantic) layer:

| Tool | api layer | wrapper layer |
|---|---|---|
| `differential_expression_by_gene` | OK (`total_matching=0`) | OK |
| `gene_response_profile` | OK | OK |
| `pathway_enrichment` (level=1, kegg) | OK (`EnrichmentResult`) | OK |

No crash reproduced. The `.iloc[0]` sites in `analysis/enrichment.py`
(1189, 1237) are both guarded by `if rows.empty:` immediately above. Conclusion:
the `[0]`/empty-DE crash class is **clean at all probed surfaces** — the known
bug is already fixed or never reached these paths. Phases 1–4 (the harness)
provide the durable, exhaustive guard so any residual instance (e.g. in tools
not hand-probed here) is caught and cannot regress.

**Phase 0 outcome:** no RISK fixes required (Tasks 0.2 / 0.3 are no-ops).
