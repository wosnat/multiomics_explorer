# KG change spec: unify DerivedMetric edge value property

**Date:** 2026-04-26
**Driver:** [docs/tool-specs/gene_derived_metrics.md](../tool-specs/gene_derived_metrics.md) (slice-1, tool 2 of 5) — reduces explorer-side Cypher complexity for the 4 edge-touching tools in the slice.
**Slice spec:** [docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md)

## Summary

Rename two DerivedMetric edge properties — `value_flag` → `value` (on `Derived_metric_flags_gene`) and `value_text` → `value` (on `Derived_metric_classifies_gene`) — so all three measurement edges expose the polymorphic measurement under a single column name `r.value`. Eliminates the `properties(r)` map-projection workaround and the `CASE dm.value_kind WHEN ...` switch on every RETURN clause that surfaces the value, across all 4 edge-traversing tools in slice 1 (`gene_derived_metrics` + the 3 `genes_by_{kind}_metric` drill-downs).

`Derived_metric_quantifies_gene.value` already uses this name — only the two non-numeric edge types need the rename. No node-side changes. No new edges or labels.

## Current state (verified live 2026-04-26)

Edge property keys per type:

| Edge type | Property keys | Value-column name |
|---|---|---|
| `Derived_metric_quantifies_gene` (numeric) | `id, metric_type, value` (+ `rank_by_metric, metric_percentile, metric_bucket` when parent `dm.rankable='true'`; + `adjusted_p_value, significant, p_value` when `dm.has_p_value='true'` — none today) | `value` ✓ |
| `Derived_metric_flags_gene` (boolean) | `id, metric_type, value_flag` | `value_flag` ✗ |
| `Derived_metric_classifies_gene` (categorical) | `id, metric_type, value_text` | `value_text` ✗ |

Edge counts (2026-04-26 live KG):

- `Derived_metric_quantifies_gene`: 5,114 edges
- `Derived_metric_flags_gene`: 4,694 edges
- `Derived_metric_classifies_gene`: 316 edges

The asymmetric naming forces the explorer side to do all of:

1. **Map-projection workaround.** `WITH g, dm, r, properties(r) AS p` before RETURN, then `p.value_flag` / `p.value_text` access. Direct `r.value_flag` access on a quantifies edge triggers a CyVer schema warning (`The label Derived_metric_quantifies_gene does not have the following properties: value_flag, value_text`); `properties(r)` returns a map and silences the static check.
2. **CASE switch on every RETURN.** `CASE dm.value_kind WHEN 'numeric' THEN p.value WHEN 'boolean' THEN p.value_flag WHEN 'categorical' THEN p.value_text END AS value`.
3. **Documentation paragraphs** in each tool spec explaining the workaround and its purpose, plus matching test classes (`test_polymorphic_value_case`, `test_properties_r_alias`).

After the rename, all three collapse to a plain `r.value AS value` in the unified `MATCH (dm)-[r:Derived_metric_quantifies_gene|Derived_metric_flags_gene|Derived_metric_classifies_gene]->(g)` clause — no map projection, no CASE, no schema warning, no spec workaround paragraphs.

## Required changes

### Property changes

| Node/Edge | Property | Change | Notes |
|---|---|---|---|
| `Derived_metric_flags_gene` | `value_flag` → `value` | rename | string `"true"` / `"false"` (current storage; see *Out of scope* below). 4,694 edges in live KG. |
| `Derived_metric_classifies_gene` | `value_text` → `value` | rename | category string. 316 edges in live KG. Must be subset of parent `dm.allowed_categories`. |
| `Derived_metric_quantifies_gene` | `value` | unchanged | float. Already uses target name. 5,114 edges. |

No new nodes, edges, indexes, or constraints. No node-property changes. The post-import rollup props on Gene / Experiment / Publication / OrganismTaxon are unaffected (they aggregate over the *parent DM*, not over edge value props).

### BioCypher / build-pipeline notes

- The two affected schema fields live in the BioCypher YAML under the per-edge `properties:` blocks (`Derived_metric_flags_gene`, `Derived_metric_classifies_gene`). Rename in the schema, then update the corresponding adapter modules that emit these edges to set `value` instead of `value_flag` / `value_text`.
- All three edge types should land with property type **`str`** in the schema (consistent with current storage). See *Out of scope*.

## Example Cypher (desired)

After the rename, `gene_derived_metrics`'s detail Cypher reduces to (only the relevant fragment shown — full builder unchanged otherwise):

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})
MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene
                          |Derived_metric_flags_gene
                          |Derived_metric_classifies_gene]->(g)
RETURN g.locus_tag AS locus_tag,
       dm.id AS derived_metric_id,
       dm.value_kind AS value_kind,
       r.value AS value,                         -- ← single column, no CASE, no projection
       CASE WHEN dm.rankable = 'true' THEN r.rank_by_metric ELSE null END AS rank_by_metric,
       CASE WHEN dm.rankable = 'true' THEN r.metric_percentile ELSE null END AS metric_percentile,
       CASE WHEN dm.rankable = 'true' THEN r.metric_bucket ELSE null END AS metric_bucket,
       ...
ORDER BY g.locus_tag, dm.value_kind, dm.id
```

Compare with the current form in [`docs/tool-specs/gene_derived_metrics.md`](../tool-specs/gene_derived_metrics.md) §"Query Builder" → `build_gene_derived_metrics`, which carries:

```cypher
WITH g, dm, r, properties(r) AS p                -- ← removed after rename
RETURN ...,
       CASE dm.value_kind                         -- ← removed after rename
         WHEN 'numeric' THEN p.value
         WHEN 'boolean' THEN p.value_flag
         WHEN 'categorical' THEN p.value_text
       END AS value,
       CASE WHEN dm.rankable = 'true' THEN p.rank_by_metric ELSE null END AS rank_by_metric,
       ...
```

Same simplification lands in the 3 `genes_by_{kind}_metric` drill-down builders (each currently picks the right edge prop name based on the kind it targets — after the rename, every builder uses `r.value` and the kind-specific RETURN lines collapse to one).

## Verification queries

Run these after KG rebuild to confirm the rename landed cleanly:

```cypher
-- 1. New `value` prop is present on the renamed edges (counts should match
--    the pre-rebuild edge counts above).
MATCH ()-[r:Derived_metric_flags_gene]->()
WHERE r.value IS NOT NULL
RETURN count(r) AS flags_with_value;
-- expected: 4,694

MATCH ()-[r:Derived_metric_classifies_gene]->()
WHERE r.value IS NOT NULL
RETURN count(r) AS classifies_with_value;
-- expected: 316

-- 2. Old prop names are gone (zero edges should still carry them).
MATCH ()-[r:Derived_metric_flags_gene]->()
WHERE r.value_flag IS NOT NULL
RETURN count(r) AS flags_with_old_prop;
-- expected: 0

MATCH ()-[r:Derived_metric_classifies_gene]->()
WHERE r.value_text IS NOT NULL
RETURN count(r) AS classifies_with_old_prop;
-- expected: 0

-- 3. Quantifies edges unchanged.
MATCH ()-[r:Derived_metric_quantifies_gene]->()
WHERE r.value IS NOT NULL
RETURN count(r) AS quantifies_with_value;
-- expected: 5,114

-- 4. Edge-key shape verification (one edge of each type).
MATCH ()-[r1:Derived_metric_quantifies_gene]->()
WITH keys(r1) AS quantifies_keys LIMIT 1
MATCH ()-[r2:Derived_metric_flags_gene]->()
WITH quantifies_keys, keys(r2) AS flags_keys LIMIT 1
MATCH ()-[r3:Derived_metric_classifies_gene]->()
RETURN quantifies_keys, flags_keys, keys(r3) AS classifies_keys LIMIT 1;
-- expected: all three include "value"; flags_keys does NOT include "value_flag";
-- classifies_keys does NOT include "value_text".

-- 5. Sample boolean values still match the storage convention (string-typed
--    "true"/"false" until the BioCypher native-bool issue is resolved upstream;
--    see *Out of scope*).
MATCH ()-[r:Derived_metric_flags_gene]->()
RETURN r.value AS sample_value, count(*) AS n
ORDER BY n DESC LIMIT 5;
-- expected: a "true" row with count 4,694 (KG currently materializes positive
-- assertions only — see slice spec §"KG invariants" §4).

-- 6. Sample categorical values are still drawn from parent allowed_categories.
MATCH (dm:DerivedMetric {value_kind: 'categorical'})-[r:Derived_metric_classifies_gene]->()
WITH dm.id AS dm_id, dm.allowed_categories AS allowed,
     collect(DISTINCT r.value) AS observed
RETURN dm_id, allowed, observed,
       all(c IN observed WHERE c IN allowed) AS values_in_allowed_set;
-- expected: values_in_allowed_set = true for every DM.
```

## Downstream impact (explorer side, after rebuild)

| File | Change |
|---|---|
| [`docs/tool-specs/gene_derived_metrics.md`](../tool-specs/gene_derived_metrics.md) | Drop the `properties(r)` projection paragraph from §"Special handling"; simplify §"Query Builder" → `build_gene_derived_metrics` Cypher; remove `test_polymorphic_value_case`, `test_properties_r_alias` from the unit-test list. |
| `docs/tool-specs/genes_by_numeric_metric.md` (forthcoming) | Will use `r.value` from day one — no workaround paragraph needed. |
| `docs/tool-specs/genes_by_boolean_metric.md` (forthcoming) | Result column `value` sources from `r.value` directly (was `r.value_flag`). |
| `docs/tool-specs/genes_by_categorical_metric.md` (forthcoming) | Result column `value` sources from `r.value` directly (was `r.value_text`). Filter param `categories` still compares to `r.value` rather than `r.value_text`. |
| `multiomics_explorer/kg/queries_lib.py` | When the 4 builders ship in phase 2, they reference `r.value` everywhere — no migration needed for already-shipped code (this affects only unwritten builders today). |

`list_derived_metrics` (already shipped) does not traverse these edges and is unaffected.

## Out of scope

- **Boolean-as-Neo4j-native.** Slice spec §"KG invariants" §6 noted that `dm.rankable`, `dm.has_p_value`, and edge `value_flag` are all stored as string `"true"` / `"false"` rather than Neo4j-native booleans, and labeled this "Internal-only — not surfaced in tool docs." The user has confirmed this is **blocked upstream by a known BioCypher limitation** (BioCypher cannot emit Neo4j-native booleans today), so no rebuild can fix it short of a BioCypher patch. The rename in this spec preserves string-typed boolean storage on the renamed `value` column for `Derived_metric_flags_gene`. When BioCypher gains native-bool emission, file a follow-up KG spec to convert `dm.rankable` / `dm.has_p_value` / `r.value` (boolean rows) to `bool` and trim the explorer-side string-coercion logic in `_list_derived_metrics_where` + the `dm.rankable = 'true' AS rankable` RETURN coercion across the DM tool family.
- **Gene-side rollup naming unification** (`g.numeric_metric_count` / `g.classifier_flag_count` / `g.classifier_label_count` → unified `g.derived_metric_count` + per-kind sub-counters). Slice spec §"KG invariants" §5 flagged this as a slice-2 concern. Not relevant to slice-1's edge-traversal Cypher, which aggregates via `apoc.coll.frequencies` on collected rows rather than via these precomputed counters. File a separate spec when slice 2 (existing-tool DM rollups) starts.
- **Edge `id` and `metric_type` props.** Both are redundant once dm is in scope (the unique edge id can be derived from `dm.id || '__' || g.locus_tag`, and `metric_type` echoes `dm.metric_type`). Removing them would shrink edge storage, but neither blocks any slice-1 Cypher and the savings are negligible at current edge volumes. Skip.
- **`adjusted_p_value` / `significant` / `p_value` columns on quantifies edges.** Forward-compat surface — surfaces only when a paper providing p-values lands. Not part of this rename.

## Status

- [x] Spec reviewed with user (2026-04-26)
- [x] Renamed in BioCypher schema YAML + adapter modules
- [x] KG rebuilt (2026-04-26)
- [x] Verification queries pass — confirmed live:
   - All 3 edge types expose keys `[id, metric_type, value]` (uniform).
   - `r.value` populated on **5,114** quantifies + **4,694** flags + **316** classifies — counts unchanged from pre-rebuild.
   - `value_flag` and `value_text` properties are absent (CyVer warns on lookup; 0 results).
   - Rankable extras intact (0 of 5,114 rankable edges missing `rank_by_metric` / `metric_percentile` / `metric_bucket`).
   - Sample boolean: `r.value = "true"` on all 4,694 flag edges (string-typed, BioCypher-bool constraint preserved as expected).
   - End-to-end builder shape verified: `MATCH (dm)-[r:Derived_metric_quantifies_gene|Derived_metric_flags_gene|Derived_metric_classifies_gene]->(g) RETURN r.value AS value, ...` returns 9 rows for PMM1714 (1 boolean / 1 categorical / 7 numeric) with **zero schema warnings**.
- [x] [`docs/tool-specs/gene_derived_metrics.md`](../tool-specs/gene_derived_metrics.md) updated to use `r.value` directly (dropped `properties(r)` projection, dropped `CASE dm.value_kind` switch in detail builder, replaced `test_polymorphic_value_case` + `test_properties_r_alias` with `test_value_is_direct_r_access`).
- [ ] Slice-spec [`Tool 4 — genes_by_boolean_metric`](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md) and [`Tool 5 — genes_by_categorical_metric`](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md) sections — light edit to align with `r.value` when those tools' phase-1 specs are written.
