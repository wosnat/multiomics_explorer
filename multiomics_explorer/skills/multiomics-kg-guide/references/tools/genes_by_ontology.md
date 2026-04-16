# genes_by_ontology

## What it does

Find (gene × term) pairs for an ontology, scoped by terms and/or level.

Three modes:
- term_ids only → gene discovery by pathway (walk DOWN).
- level only → pathway definitions at level N (walk UP).
- level + term_ids → scoped rollup (walk UP, restrict to given terms).

Single-organism enforced. Default `limit=500` because this tool feeds
enrichment (pathway_enrichment). For term discovery, chain from
search_ontology. For per-gene ontology details, use gene_ontology_terms.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite') | — | Ontology for these term_ids / this level. |
| organism | string | — | Organism (case-insensitive substring match, e.g. 'MED4'). Required — single-valued. Use list_organisms for valid values. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. |
| level | int \| None | None | Hierarchy level to roll UP to. 0 = broadest. At least one of `level` or `term_ids` must be provided. |
| term_ids | list[string] \| None | None | Ontology term IDs (from search_ontology). Mode 1 (no `level`): expand DOWN from each input term. Mode 3 (with `level`): scope rollup to these level-N terms. |
| min_gene_set_size | int | 5 | Exclude terms with fewer organism-scoped genes than this. |
| max_gene_set_size | int | 500 | Exclude terms with more organism-scoped genes than this. |
| summary | bool | False | If true, omit `results` (envelope only). |
| verbose | bool | False | Include function_description and sparse level_is_best_effort. |
| limit | int | 500 | Max rows returned. Default 500 — this tool feeds enrichment. |
| offset | int | 0 | Skip N rows before limit |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
ontology, organism_name, total_matching, total_genes, total_terms, total_categories, genes_per_term_min, genes_per_term_median, genes_per_term_max, terms_per_gene_min, terms_per_gene_median, terms_per_gene_max, by_category, by_level, top_terms, n_best_effort_terms, not_found, wrong_ontology, wrong_level, filtered_out, returned, offset, truncated, results
```

- **ontology** (string): Echo of input ontology (e.g. 'go_bp')
- **organism_name** (string): Single organism for all results
- **total_matching** (int): (gene × term) row count matching all filters
- **total_genes** (int): Distinct genes across results
- **total_terms** (int): Distinct terms emitted
- **total_categories** (int): Distinct gene_category values
- **genes_per_term_min** (int): Fewest genes in any surviving term
- **genes_per_term_median** (float): Median genes per term
- **genes_per_term_max** (int): Most genes in any surviving term
- **terms_per_gene_min** (int): Fewest terms for any gene
- **terms_per_gene_median** (float): Median terms per gene
- **terms_per_gene_max** (int): Most terms for any gene
- **by_category** (list[OntologyCategoryBreakdown]): Distinct-gene counts per gene_category, sorted desc
- **by_level** (list[OntologyLevelBreakdown]): Per-level summary, sorted by level asc
- **top_terms** (list[OntologyTermBreakdown]): Top 5 terms by distinct-gene count, tie-break term_id asc
- **n_best_effort_terms** (int): Distinct best-effort terms (GO-only marker; 0 for other ontologies)
- **not_found** (list[string]): Input term_ids absent from the KG entirely
- **wrong_ontology** (list[string]): Input term_ids present but in a different ontology label
- **wrong_level** (list[string]): Input term_ids in the ontology but at wrong level (Mode 3 only)
- **filtered_out** (list[string]): Input term_ids valid but outside [min, max]_gene_set_size
- **returned** (int): Rows in this response
- **offset** (int): Offset into full result set
- **truncated** (bool): True when total_matching > offset + returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III, beta subunit') |
| gene_category | string \| None (optional) | Functional category (e.g. 'Replication and repair') |
| term_id | string | Ontology term ID (e.g. 'go:0050896') |
| term_name | string | Term name (e.g. 'response to stimulus') |
| level | int | Hierarchy level of this term (0 = broadest) |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| function_description | string \| None (optional) | Curated functional description (verbose only) |
| level_is_best_effort | bool \| None (optional) | True when GO term's level is best-effort min-path (sparse: absent for non-GO or non-best-effort; verbose only) |

## Few-shot examples

### Example 1: Mode 1 — gene discovery by pathway (term_ids only)

```example-call
genes_by_ontology(ontology="go_bp", organism="MED4", term_ids=["go:0006260"])
```

```example-response
{"ontology": "go_bp", "organism_name": "Prochlorococcus MED4", "total_matching": 30, "total_genes": 30, "total_terms": 1, "total_categories": 1, "by_level": [{"level": 6, "n_terms": 1, "n_genes": 30, "row_count": 30}], "top_terms": [{"term_id": "go:0006260", "term_name": "DNA replication", "count": 30}], "n_best_effort_terms": 0, "not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": [], "returned": 5, "truncated": true, "offset": 0, "results": [{"locus_tag": "PMM0001", "gene_name": "dnaN", "product": "DNA polymerase III", "gene_category": "Replication", "term_id": "go:0006260", "term_name": "DNA replication", "level": 6}]}
```

### Example 2: Mode 2 — pathway definitions at level N (level only)

```example-call
genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
```

```example-response
{"ontology": "cyanorak_role", "organism_name": "Prochlorococcus MED4", "total_matching": 1740, "total_genes": 1100, "total_terms": 69, "by_level": [{"level": 1, "n_terms": 69, "n_genes": 1100, "row_count": 1740}], "top_terms": [{"term_id": "cyanorak.role:A.1", "term_name": "...", "count": 120}], "returned": 500, "truncated": true, "results": [...]}
```

### Example 3: Mode 3 — scope rollup to specific pathways (level + term_ids)

```example-call
genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1, term_ids=["cyanorak.role:A.1", "cyanorak.role:A.2"])
```

### Example 4: Summary-only (envelope, no rows)

```example-call
genes_by_ontology(ontology="go_bp", organism="MED4", level=1, summary=True)
```

### Example 5: BRITE tree-scoped rollup (transporters at category level)

```example-call
genes_by_ontology(ontology="brite", organism="MED4", level=1, tree="transporters")
```

### Example 6: Inspect all terms (override size filter)

```example-call
genes_by_ontology(ontology="go_bp", organism="MED4", level=1, min_gene_set_size=0, max_gene_set_size=100000)
```

### Example 7: From level-survey to pathway defs

```
Step 1: ontology_landscape(organism="MED4")
        → identify best (ontology, level) pair, e.g. (cyanorak_role, level=1)

Step 2: genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
        → get TERM2GENE pathway definitions at that level

Step 3: pathway_enrichment(ontology="cyanorak_role", organism="MED4", level=1, experiment_ids=[...])
        → run ORA with those pathway definitions
```

## Chaining patterns

```
ontology_landscape → genes_by_ontology(level=N)
search_ontology → genes_by_ontology(term_ids=[...])
genes_by_ontology → pathway_enrichment
genes_by_ontology → gene_overview
```

## Common mistakes

- At least one of `level` or `term_ids` must be set — calling without either is an error.

- Results are `(gene × term)` pairs, not distinct genes — use `total_genes` for the gene count. `total_matching` is the row count.

- Gene-set-size filter is organism-scoped via descendants — count of distinct genes annotated to the term or any descendant for `$organism`. Matches `ontology_landscape`'s convention.

- For GO (a DAG), level slicing is a best-effort approximation — `level_is_best_effort` flags rows where the min-path to root was ambiguous. Check `ontology_landscape`'s `best_effort_share` per level.

- `level_is_best_effort` is a sparse column — absent when not GO / not best-effort. In pandas, call `df['level_is_best_effort'].fillna(False)` before boolean filtering.

- `organism` is required and single-valued. For cross-organism browsing, loop the tool or use `gene_ontology_terms`.

- Pfam is a 2-level ontology: `level=1` → Pfam domains (leaf), `level=0` → PfamClan (parent). Both kinds of IDs are accepted under `ontology='pfam'`.

- KEGG: gene edges only hit the KO leaf (`level=3`). Passing `level=0/1/2` rolls up to category/subcategory/pathway via `is_a`.

- BRITE: gene edges hit the KO leaf (`level=3`, same as KEGG). Passing `level=0/1/2` rolls up through BRITE tree hierarchy. Each BRITE tree is a separate functional classification — use `tree` to scope to a specific tree (e.g. `tree='transporters'`). Without `tree`, results mix all BRITE trees. Use `list_filter_values('brite_tree')` to discover available trees.

- Flat ontologies (`cog_category`, `tigr_role`) have only `level=0`. Passing `level >= 1` in Mode 2 returns empty results; in Mode 3 the ids route to `wrong_level`.

```mistake
genes_by_ontology(ontology='go_bp', organism='MED4')  # no level or term_ids
```

```correction
genes_by_ontology(ontology='go_bp', organism='MED4', level=3)
```

```mistake
len(response.results)  # wrong — that's the row count after limit
```

```correction
response.total_genes  # distinct genes across all matches
```

## Package import equivalent

```python
from multiomics_explorer import genes_by_ontology

result = genes_by_ontology(ontology=..., organism=...)
# returns dict with keys: ontology, organism_name, total_matching, total_genes, total_terms, total_categories, genes_per_term_min, genes_per_term_median, genes_per_term_max, terms_per_gene_min, terms_per_gene_median, terms_per_gene_max, by_category, by_level, top_terms, n_best_effort_terms, not_found, wrong_ontology, wrong_level, filtered_out, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
