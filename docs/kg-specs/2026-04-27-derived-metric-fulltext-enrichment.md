# KG change spec: derived-metric-fulltext-enrichment

## Summary

Two coordinated KG-side changes for explorer slice 2 (one rebuild covers both):

1. **Fulltext enrichment** — add `derived_metric_search_text: str` property on `Experiment` + `Publication`; extend `experimentFullText` + `publicationFullText` indexes to cover it. Tokens come from each node's reachable DerivedMetrics (`name`, `metric_type` token-split, `field_description`, `compartment`). Makes `list_experiments(search_text=...)` / `list_publications(search_text=...)` natural DM-discovery channels.
2. **Gene-rollup rename** — `Gene.classifier_flag_*` → `Gene.boolean_metric_*`, `Gene.classifier_label_*` → `Gene.categorical_metric_*`. Cleans up slice-1 KG-side legacy naming. Internal-only, no external users.

Driven by `multiomics_explorer/docs/superpowers/specs/2026-04-27-discovery-dm-awareness-design.md` (decisions D5, D8). `geneFullText` is intentionally **not** changed (would conflate gene function with what was *measured* on the gene — see slice-2 spec D5).

## Current state

Verified live 2026-04-27.

### Existing fulltext indexes

```
experimentFullText  — Experiment.{name, treatment, control, experimental_context, light_condition}
publicationFullText — Publication.{title, abstract, description}
geneFullText        — Gene.{gene_summary, all_identifiers, gene_name_synonyms, alternate_functional_descriptions}
```

Both target indexes use:
- `indexProvider: fulltext-1.0`
- `fulltext.analyzer: standard-no-stop-words`
- `fulltext.eventually_consistent: false`

These options must round-trip on drop+recreate.

### DerivedMetric nodes and edges

```
34 DerivedMetric nodes total
  whole_cell: 21 (14 boolean + 6 numeric + 1 categorical)
  vesicle:    13 (9 numeric + 2 boolean + 2 categorical)

Relationships:
  (Experiment)-[:ExperimentHasDerivedMetric]->(DerivedMetric)   34 edges
  (Publication)-[:PublicationHasDerivedMetric]->(DerivedMetric) 34 edges
```

DM-bearing nodes (sparse):
- 10 of 172 Experiments have ≥1 DM (5.8%)
- 5 of 38 Publications have ≥1 DM (13%)

### Existing Gene properties (D8 source)

```
g.classifier_flag_count             → boolean DM count for this gene
g.classifier_flag_types_observed    → list of boolean metric_types observed
g.classifier_label_count            → categorical DM count
g.classifier_label_types_observed   → list of categorical metric_types observed
```

These are the four properties to be renamed.

## Required changes

### New nodes

None.

### New edges

None.

### Property changes

| Node | Property | Change | Notes |
|---|---|---|---|
| Experiment | `derived_metric_search_text` | **add** (str) | Computed during post-import: aggregate of DM tokens for DMs reached via `(:Experiment)-[:ExperimentHasDerivedMetric]->(:DerivedMetric)`. Tokens: DM `name`, DM `metric_type` (snake_case → space-tokenized), DM `field_description`, DM `compartment`. Concatenated with single-space separator. **Stored as `null` when no DMs reachable** (do not store empty/whitespace string — Neo4j fulltext indexes skip nulls but would still index a whitespace string). |
| Publication | `derived_metric_search_text` | **add** (str) | Same shape, sourced via `(:Publication)-[:PublicationHasDerivedMetric]->(:DerivedMetric)`. |
| Gene | `classifier_flag_count` | **rename →** `boolean_metric_count` | Type unchanged (int). |
| Gene | `classifier_flag_types_observed` | **rename →** `boolean_metric_types_observed` | Type unchanged (list[str]). |
| Gene | `classifier_label_count` | **rename →** `categorical_metric_count` | Type unchanged (int). |
| Gene | `classifier_label_types_observed` | **rename →** `categorical_metric_types_observed` | Type unchanged (list[str]). |

### Index changes

| Index | Action | Properties (after) | Options |
|---|---|---|---|
| `experimentFullText` | drop + recreate | `name`, `treatment`, `control`, `experimental_context`, `light_condition`, **`derived_metric_search_text`** | analyzer `standard-no-stop-words`; `eventually_consistent: false` |
| `publicationFullText` | drop + recreate | `title`, `abstract`, `description`, **`derived_metric_search_text`** | analyzer `standard-no-stop-words`; `eventually_consistent: false` |
| `geneFullText` | **unchanged** | (intentional — function/measurement category-error guard) | — |

## Example Cypher (desired)

### Aggregation logic — verified against current KG 2026-04-27

The post-import code should compute `derived_metric_search_text` equivalent to this Cypher (which produces the desired tokens, but runs at import-time in Python rather than at query-time):

```cypher
// Per-experiment search text
MATCH (e:Experiment)-[:ExperimentHasDerivedMetric]->(dm:DerivedMetric)
WITH e,
     collect(DISTINCT dm.name)              AS names,
     collect(DISTINCT dm.metric_type)       AS metric_types,
     collect(DISTINCT dm.field_description) AS descs,
     collect(DISTINCT dm.compartment)       AS comps
WITH e,
     apoc.text.join(names, ' ') + ' '
   + apoc.text.replace(apoc.text.join(metric_types, ' '), '_', ' ') + ' '
   + apoc.text.join(descs, ' ') + ' '
   + apoc.text.join(comps, ' ') AS derived_metric_search_text
RETURN e.id AS experiment_id, derived_metric_search_text;

// Per-publication search text — same shape via PublicationHasDerivedMetric
MATCH (p:Publication)-[:PublicationHasDerivedMetric]->(dm:DerivedMetric)
WITH p,
     collect(DISTINCT dm.name)              AS names,
     collect(DISTINCT dm.metric_type)       AS metric_types,
     collect(DISTINCT dm.field_description) AS descs,
     collect(DISTINCT dm.compartment)       AS comps
RETURN p.doi AS doi,
       apoc.text.join(names, ' ') + ' '
     + apoc.text.replace(apoc.text.join(metric_types, ' '), '_', ' ') + ' '
     + apoc.text.join(descs, ' ') + ' '
     + apoc.text.join(comps, ' ') AS derived_metric_search_text;
```

Sample produced text (verified, Waldbauer 2012 paired-diel experiment):

```
Time of peak transcript abundance (h) Time of peak protein abundance (h)
Protein-transcript lag (h) Transcript amplitude (log2) Protein amplitude (log2)
Transcript:protein amplitude ratio
peak time transcript h peak time protein h protein transcript lag h
diel amplitude transcript log2 diel amplitude protein log2 damping ratio
... [field_descriptions] ... whole_cell
```

Char length distribution across the 10 DM-bearing experiments: 687 – 1157 chars.
Across the 5 DM-bearing publications: 909 – 1641 chars. Tiny payload per node.

### Index recreation (Cypher)

```cypher
DROP INDEX experimentFullText;
CREATE FULLTEXT INDEX experimentFullText FOR (e:Experiment)
ON EACH [e.name, e.treatment, e.control, e.experimental_context,
         e.light_condition, e.derived_metric_search_text]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words',
    `fulltext.eventually_consistent`: false
  }
};

DROP INDEX publicationFullText;
CREATE FULLTEXT INDEX publicationFullText FOR (p:Publication)
ON EACH [p.title, p.abstract, p.description, p.derived_metric_search_text]
OPTIONS {
  indexConfig: {
    `fulltext.analyzer`: 'standard-no-stop-words',
    `fulltext.eventually_consistent`: false
  }
};
```

### Rename strategy

Property renames happen in the post-import code that materializes Gene rollups (the KG repo's biocypher post-import step). The new names are written directly; no migration query is needed because the KG is rebuilt from scratch on each load.

## Verification queries

Run after KG rebuild to confirm both changes landed.

### Fulltext enrichment

```cypher
// 1. Property populated for all DM-bearing experiments
MATCH (e:Experiment) WHERE e.derived_metric_count > 0
RETURN count(*) AS expected_with_search_text,
       count(e.derived_metric_search_text) AS actual_with_search_text;
// Expect: 10 == 10 (today)

// 2. Property null on non-DM experiments
MATCH (e:Experiment) WHERE e.derived_metric_count = 0
RETURN count(*) AS non_dm_experiments,
       count(e.derived_metric_search_text) AS leftover_search_text;
// Expect: 162, 0

// 3. Same checks on Publication
MATCH (p:Publication) WHERE p.derived_metric_count > 0
RETURN count(*) AS expected, count(p.derived_metric_search_text) AS actual;
// Expect: 5 == 5

// 4. DM-token search hits expected experiments
CALL db.index.fulltext.queryNodes('experimentFullText', 'diel amplitude')
YIELD node, score
RETURN count(*) AS hits, collect(node.id)[0..3] AS sample_ids;
// Expect: ≥ 1 hit; sample includes Waldbauer 2012 paired-diel experiment

// 5. DM-token search via metric_type underscore-split
CALL db.index.fulltext.queryNodes('publicationFullText', 'damping ratio')
YIELD node, score
RETURN count(*) AS hits, collect(node.doi) AS dois;
// Expect: ≥ 1 hit including 10.1371/journal.pone.0043432

// 6. Vesicle-compartment token reaches publication search
CALL db.index.fulltext.queryNodes('publicationFullText', 'vesicle proteome')
YIELD node, score
RETURN count(*) AS hits;
// Expect: ≥ 1 (Biller 2014 / 2022 vesicle proteomics papers)

// 7. geneFullText unchanged (regression guard for D5)
SHOW FULLTEXT INDEXES YIELD name, properties
WHERE name = 'geneFullText'
RETURN properties;
// Expect: ['gene_summary', 'all_identifiers', 'gene_name_synonyms',
//          'alternate_functional_descriptions']

// 8. Index options preserved
SHOW FULLTEXT INDEXES YIELD name, options
WHERE name IN ['experimentFullText', 'publicationFullText']
RETURN name, options.indexConfig.`fulltext.analyzer` AS analyzer;
// Expect: both 'standard-no-stop-words'
```

### Gene rename (D8)

```cypher
// 9. New names populated everywhere old names were; old keys gone.
//    Capture pre-rebuild baselines via the running KG before rebuild,
//    then assert the post-rebuild numbers equal them.
MATCH (g:Gene) WHERE g.boolean_metric_count IS NOT NULL
WITH count(*) AS post_rename_genes
MATCH (g:Gene) WHERE g.classifier_flag_count IS NOT NULL
RETURN post_rename_genes, count(*) AS legacy_leftover_genes;
// Expect: post_rename_genes == pre-rebuild count of g.classifier_flag_count IS NOT NULL;
//         legacy_leftover_genes == 0

MATCH (g:Gene) WHERE g.categorical_metric_count IS NOT NULL
WITH count(*) AS post_rename_genes
MATCH (g:Gene) WHERE g.classifier_label_count IS NOT NULL
RETURN post_rename_genes, count(*) AS legacy_leftover_genes;
// Expect: post_rename_genes == pre-rebuild count of g.classifier_label_count IS NOT NULL;
//         legacy_leftover_genes == 0

// 10. Type lists renamed and populated
MATCH (g:Gene) WHERE g.boolean_metric_count > 0
RETURN count(*) AS genes_with_boolean_dms,
       count(g.boolean_metric_types_observed) AS genes_with_types_list;
// Expect: equal counts; types list is non-null wherever count > 0

// 11. No legacy keys leak through any tool
MATCH (g:Gene)
WHERE g.classifier_flag_count IS NOT NULL
   OR g.classifier_flag_types_observed IS NOT NULL
   OR g.classifier_label_count IS NOT NULL
   OR g.classifier_label_types_observed IS NOT NULL
RETURN count(*) AS legacy_property_leftovers;
// Expect: 0
```

## Status

- [x] Spec reviewed with user (slice-2 design approved 2026-04-27)
- [ ] Changes implemented in KG repo (`multiomics_biocypher_kg`)
- [ ] KG rebuilt
- [ ] Verification queries pass
- [ ] Explorer-side `tests/regression/test_regression/gene_details_*.yml` baselines regenerated via `pytest tests/regression/ --force-regen -m kg`
