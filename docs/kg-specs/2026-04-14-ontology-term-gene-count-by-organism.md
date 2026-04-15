# KG Spec: `gene_count_by_organism` map on ontology-term nodes

**Status:** Backlog (optional fast-path for explorer enrichment surface)
**Date:** 2026-04-14
**Consumer:** `multiomics_explorer` — `ontology_landscape`, `genes_by_ontology` (redefinition), future `pathway_enrichment`
**Scope:** KG-repo post-import + schema_config only. Pure addition, sparse-safe.

## Motivation

The enrichment surface's core filter is "terms whose organism-scoped gene-set size
falls within `[min_gene_set_size, max_gene_set_size]`." Today this requires an
O(genes × hierarchy-walk) aggregate per query. Landscape computes it on every
call; `genes_by_ontology` (redefinition) will do the same unless the count is
precomputed.

Precomputing it at rebuild time turns the filter into an O(terms_at_level)
property lookup.

## Proposal

Add property **`gene_count_by_organism: map<str,int>`** to every ontology-term
node label. Key = `g.organism_name`. Value = distinct genes reachable via
hierarchy descendants (same semantics landscape and `genes_by_ontology` use).

Labels to patch (10):
`BiologicalProcess, MolecularFunction, CellularComponent, EcNumber, KeggTerm,
CogFunctionalCategory, CyanorakRole, TigrRole, Pfam, PfamClan`

Sparse: organisms with zero reachable genes are omitted from the map (not
stored as `0`) — keeps maps small and matches the "property only when
populated" convention.

## Cost (measured against live KG, 2026-04-14)

| Dimension | Cost |
|---|---|
| Build time, one-time post-import | ~2s GO BP (3052 terms × 17 orgs); **~5–15s total** across all 10 ontologies |
| Storage | ~22.6 MB across ~24,600 term nodes |
| Schema config | `gene_count_by_organism: map<str,int>` × 10 node labels |
| Post-import Cypher | ~100 lines (one template, 10 ontologies) |
| Migration | Pure addition; no renames; backwards compatible |
| Risk | Low — simple aggregation, no semantic change |

## Post-import Cypher pattern

One block per ontology. Template (shown for GO BP):

```cypher
CALL () {
  MATCH (t:BiologicalProcess)
  OPTIONAL MATCH (t)
    <-[:Biological_process_is_a_biological_process
      |Biological_process_part_of_biological_process*0..]-
    (leaf:BiologicalProcess)
    <-[:Gene_involved_in_biological_process]-(g:Gene)
  WITH t, g.organism_name AS org, count(DISTINCT g) AS n
  WHERE org IS NOT NULL
  WITH t, apoc.map.fromPairs(collect([org, n])) AS counts
  SET t.gene_count_by_organism = counts
} IN TRANSACTIONS OF 500 ROWS;
```

Per-ontology variations:
- **Walk direction:** `<-[:...*0..]-` (from root down to leaf), because the
  canonical `is_a` / `part_of` / `Cyanorak_role_is_a_cyanorak_role` etc.
  edges go `(child)-[:rel]->(parent)`.
- **Flat ontologies** (`cog_category`, `tigr_role`): no hierarchy walk;
  bind leaf directly to gene edge.
- **Pfam (level 1)**: direct-annotation count (leaf, no descendants).
- **PfamClan (level 0)**: walk `(clan:PfamClan)<-[:Pfam_in_pfam_clan]-(pfam:Pfam)<-[:Gene_has_pfam]-(g:Gene)` and aggregate organism-scoped counts.
  This corrects the `ontology_landscape` flat-Pfam shortcut; Pfam is genuinely 2-level per the KG (`Pfam.level=1`, `PfamClan.level=0`) and the property should reflect that.
- **KEGG**: gene edges terminate only at `level_kind='ko'` leaves (i.e.
  `level=3`). Walk up via `Kegg_term_is_a_kegg_term`.

Each block mirrors the landscape query's walk pattern — verified at runtime.

## Consumer usage in explorer (post-landing)

Fast-path filter in `genes_by_ontology` Mode 2:

```cypher
MATCH (t:BiologicalProcess)
WHERE t.level = $level
  AND coalesce(t.gene_count_by_organism[$org], 0) >= $min_size
  AND coalesce(t.gene_count_by_organism[$org], 0) <= $max_size
// ... then walk and emit gene × term pairs for the surviving term set
```

Same pattern reusable in `ontology_landscape`, `pathway_enrichment`, and
diagnostic queries ("which terms have 0 genes in MED4?").

## Validation / tests

- Unit in KG repo: `tests/test_ontology_gene_counts.py` — assert
  `t.gene_count_by_organism[org]` equals the landscape-computed count for a
  sample of (term, organism) pairs across all 10 labels.
- Cross-check: sum over map values for leaf-direct ontologies must equal
  `count((leaf)<-[:gene_rel]-(g))`.

## Rollout

Single KG rebuild, alongside other post-import computations. No migration
script needed.

## Out of scope

- Per-experiment gene counts (would require joining through
  `Changes_expression_of` and become orders of magnitude more expensive).
  Keep that on `Experiment` nodes if/when needed.
- Any lookup indexing — `gene_count_by_organism` is a map, not a filter key;
  callers read by `$org`.
