# discussed_by_publication

## What it does

Literature index: publication DOIs to the genes and KEGG pathways each paper names in prose, with a prominence label — recall-biased, never DE-table data.

Use for what a paper names; its DE results come from `list_experiments` then `differential_expression_by_gene`. Pathways return verbatim — chain `genes_by_ontology(ontology='kegg')` for genes.
Filters: publication_dois, entity_kind, prominence.
Returns: by_entity_kind, by_prominence, top_kegg_pathways, not_found, not_matched; one row = (doi, entity_kind, entity_id, prominence).
docs://tools/discussed_by_publication; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| publication_dois | list[string] | — | Restrict to these publication DOIs. |
| entity_kind | string ('gene', 'kegg_pathway') \| None | None | Restrict to one arm: 'gene' or 'kegg_pathway'. None = both. |
| prominence | string ('central', 'peripheral') \| None | None | Filter edges by prominence: 'central' or 'peripheral'. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, returned, offset, truncated, by_entity_kind, by_prominence, top_kegg_pathways, top_publications, not_found, not_matched, results
```

- **total_entries** (int): All discusses edges from matched DOIs, BEFORE entity_kind / prominence filters.
- **total_matching** (int): Rows after entity_kind / prominence filters (full filtered count, not the offset slice).
- **returned** (int): Detail rows in this response (0 when summary=true).
- **offset** (int): Offset into the filtered result set (pagination).
- **truncated** (bool): True if total_matching > returned.
- **by_entity_kind** (list[DiscussedByEntityKindBreakdown]): Row counts per entity kind over the filtered set.
- **by_prominence** (list[DiscussedByProminenceBreakdown]): Row counts per prominence over the filtered set.
- **top_kegg_pathways** (list[DiscussedTopKeggPathway]): Discussed KEGG pathways across the input DOIs, ranked by mention count. Feed an id into genes_by_ontology(ontology='kegg').
- **top_publications** (list[DiscussedTopPublication]): Input DOIs ranked by their discussed-edge count — surfaces the densest narrative index in a batch.
- **not_found** (list[string]): Input DOIs absent from the KG.
- **not_matched** (list[string]): Input DOIs present but with no discusses edge after filters.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| doi | string | Publication DOI that discusses this entity (e.g. '10.1038/ismej.2016.70'). |
| entity_kind | string ('gene', 'kegg_pathway') | Discussed entity type: 'gene' or 'kegg_pathway'. |
| entity_id | string | Verbatim node id — bare gene locus_tag (e.g. 'PMT1030') or prefixed KEGG pathway id (e.g. 'kegg.pathway:ko00710'). |
| entity_name | string | Readable entity name — gene gene_name (falls back to product) or KEGG pathway name. |
| organism | string \| None (optional) | Organism of the gene (e.g. 'Prochlorococcus MED4'); explicit None on kegg_pathway rows (union padding). |
| prominence | string ('central', 'peripheral') | How prominently the paper discusses the entity: 'central' (a focus) or 'peripheral' (a passing mention). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| evidence | string \| None (optional) | Extraction quote supporting the mention (verbose-only; None compact). |

## Few-shot examples

### Example 1: What does a paper discuss?

```example-call
discussed_by_publication(publication_dois=["10.1038/ismej.2016.70"])
```

```example-response
{
  "total_entries": 37,
  "total_matching": 37,
  "returned": 37,
  "offset": 0,
  "truncated": false,
  "by_entity_kind": [{"entity_kind": "gene", "count": 29}, {"entity_kind": "kegg_pathway", "count": 8}],
  "by_prominence": [{"prominence": "peripheral", "count": 20}, {"prominence": "central", "count": 17}],
  "top_kegg_pathways": [
    {"id": "kegg.pathway:ko00010", "name": "Glycolysis / Gluconeogenesis", "n": 1},
    {"id": "kegg.pathway:ko00710", "name": "Carbon fixation by Calvin cycle", "n": 1},
    {"id": "kegg.pathway:ko00030", "name": "Pentose phosphate pathway", "n": 1},
    {"id": "kegg.pathway:ko00061", "name": "Fatty acid biosynthesis", "n": 1},
    {"id": "kegg.pathway:ko00860", "name": "Porphyrin metabolism", "n": 1},
    ...
  ],
  "top_publications": [
    {
      "doi": "10.1038/ismej.2016.70",
      "title": "Transcriptional response of Prochlorococcus to co-culture with a marine Alteromonas: differences between strains and ...",
      "n": 37
    }
  ],
  "not_found": [],
  "not_matched": [],
  "results": [
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "gene",
      "entity_id": "PMT0238",
      "entity_name": "bacteriocin-type signal sequence",
      "organism": "Prochlorococcus MIT9313",
      "prominence": "central",
      "evidence": null
    },
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "gene",
      "entity_id": "PMT0246",
      "entity_name": "possible Profilin",
      "organism": "Prochlorococcus MIT9313",
      "prominence": "central",
      "evidence": null
    },
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "gene",
      "entity_id": "PMT0925",
      "entity_name": "conserved hypothetical protein",
      "organism": "Prochlorococcus MIT9313",
      "prominence": "central",
      "evidence": null
    },
    ...
  ]
}
```

### Example 2: Restrict to the KEGG-pathway arm only

```example-call
discussed_by_publication(publication_dois=["10.1038/ismej.2016.70"], entity_kind="kegg_pathway")
```

```example-response
{
  "total_entries": 37,
  "total_matching": 8,
  "returned": 8,
  "offset": 0,
  "truncated": false,
  "by_entity_kind": [{"entity_kind": "kegg_pathway", "count": 8}],
  "by_prominence": [{"prominence": "peripheral", "count": 6}, {"prominence": "central", "count": 2}],
  "top_kegg_pathways": [
    {"id": "kegg.pathway:ko00010", "name": "Glycolysis / Gluconeogenesis", "n": 1},
    {"id": "kegg.pathway:ko00710", "name": "Carbon fixation by Calvin cycle", "n": 1},
    {"id": "kegg.pathway:ko00030", "name": "Pentose phosphate pathway", "n": 1},
    {"id": "kegg.pathway:ko00061", "name": "Fatty acid biosynthesis", "n": 1},
    {"id": "kegg.pathway:ko00860", "name": "Porphyrin metabolism", "n": 1},
    ...
  ],
  "top_publications": [
    {
      "doi": "10.1038/ismej.2016.70",
      "title": "Transcriptional response of Prochlorococcus to co-culture with a marine Alteromonas: differences between strains and ...",
      "n": 8
    }
  ],
  "not_found": [],
  "not_matched": [],
  "results": [
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "kegg_pathway",
      "entity_id": "kegg.pathway:ko00195",
      "entity_name": "Photosynthesis",
      "organism": null,
      "prominence": "central",
      "evidence": null
    },
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "kegg_pathway",
      "entity_id": "kegg.pathway:ko01230",
      "entity_name": "Biosynthesis of amino acids",
      "organism": null,
      "prominence": "central",
      "evidence": null
    },
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "kegg_pathway",
      "entity_id": "kegg.pathway:ko00010",
      "entity_name": "Glycolysis / Gluconeogenesis",
      "organism": null,
      "prominence": "peripheral",
      "evidence": null
    },
    ...
  ]
}
```

### Example 3: Only the prominently-discussed (central) entities

```example-call
discussed_by_publication(publication_dois=["10.1038/ismej.2016.70"], prominence="central")
```

### Example 4: Summary only (no detail rows)

```example-call
discussed_by_publication(publication_dois=["10.1038/ismej.2016.70"], summary=True)
```

### Example 5: See why a paper discusses each entity (verbose evidence quote)

```example-call
discussed_by_publication(publication_dois=["10.1038/ismej.2016.70"], entity_kind="kegg_pathway", verbose=True)
```

```example-response
{
  "total_entries": 37,
  "total_matching": 8,
  "returned": 8,
  "offset": 0,
  "truncated": false,
  "by_entity_kind": [{"entity_kind": "kegg_pathway", "count": 8}],
  "by_prominence": [{"prominence": "peripheral", "count": 6}, {"prominence": "central", "count": 2}],
  "top_kegg_pathways": [
    {"id": "kegg.pathway:ko00010", "name": "Glycolysis / Gluconeogenesis", "n": 1},
    {"id": "kegg.pathway:ko00710", "name": "Carbon fixation by Calvin cycle", "n": 1},
    {"id": "kegg.pathway:ko00030", "name": "Pentose phosphate pathway", "n": 1},
    {"id": "kegg.pathway:ko00061", "name": "Fatty acid biosynthesis", "n": 1},
    {"id": "kegg.pathway:ko00860", "name": "Porphyrin metabolism", "n": 1},
    ...
  ],
  "top_publications": [
    {
      "doi": "10.1038/ismej.2016.70",
      "title": "Transcriptional response of Prochlorococcus to co-culture with a marine Alteromonas: differences between strains and ...",
      "n": 8
    }
  ],
  "not_found": [],
  "not_matched": [],
  "results": [
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "kegg_pathway",
      "entity_id": "kegg.pathway:ko00195",
      "entity_name": "Photosynthesis",
      "organism": null,
      "prominence": "central",
      "evidence": "expression of genes involved in photosynthesis ... decreased in MED4 and increased in MIT9313 (Abstract, p1; Results,..."
    },
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "kegg_pathway",
      "entity_id": "kegg.pathway:ko01230",
      "entity_name": "Biosynthesis of amino acids",
      "organism": null,
      "prominence": "central",
      "evidence": "genes involved in the biosynthesis of amino acids ... less abundantly expressed in MED4+1A3 (p6, Results)"
    },
    {
      "doi": "10.1038/ismej.2016.70",
      "entity_kind": "kegg_pathway",
      "entity_id": "kegg.pathway:ko00010",
      "entity_name": "Glycolysis / Gluconeogenesis",
      "organism": null,
      "prominence": "peripheral",
      "evidence": "Glycolysis (0596, 0185*) (Table 2, p7)"
    },
    ...
  ]
}
```

### Example 6: From paper to discussed entities to drill-down

```
Step 1: list_publications(search_text="co-culture")
        → find the paper, copy its doi

Step 2: discussed_by_publication(publication_dois=["10.1038/ismej.2016.70"])
        → the genes + KEGG pathways the paper names in prose

Step 3a: gene_overview(locus_tags=["PMT2118", "PMT_1030"])
        → data-availability rollup for the discussed genes

Step 3b: genes_by_ontology(ontology="kegg", organism="Prochlorococcus MIT9313", term_ids=["kegg.pathway:ko00710"])
        → expand a discussed pathway to its member genes
        (this tool does NOT expand pathways — it returns the terms verbatim)
```

## Chaining patterns

```
list_publications → discussed_by_publication
discussed_by_publication → gene_overview
discussed_by_publication → genes_by_ontology(ontology='kegg', term_ids=[...])
discussed_by_publication(entity_kind='gene') → gene_overview → differential_expression_by_gene
discussed_by_publication(entity_kind='kegg_pathway') → genes_by_ontology(ontology='kegg', term_ids=[pathway_id]) → pathway_enrichment
```

## Common mistakes

- This is a recall-biased narrative literature index — the genes and pathways a paper names in prose, NOT exhaustive coverage and NOT the supplementary DE-table expression data. Only about 1,000 distinct genes are named across the whole corpus (out of ~127k). For expression, use differential_expression_by_gene.

- It returns the KEGG pathway terms the paper discusses verbatim — it does NOT expand a pathway to its member genes. To get genes in a discussed pathway, chain into genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...).

- entity_id is the raw node id: gene rows carry the bare locus_tag (e.g. PMT2118); kegg_pathway rows carry the prefixed id (e.g. kegg.pathway:ko00710). Feed gene ids to gene_overview, pathway ids to genes_by_ontology(ontology='kegg').

- Rows are polymorphic: organism is populated only on gene rows; on kegg_pathway rows it is null (union padding). Likewise entity_name is the gene's gene_name (falling back to product) on gene rows and the pathway name on pathway rows.

- total_entries counts all discusses edges from the matched DOIs before any entity_kind / prominence filter; total_matching reflects the filtered set. A small total_matching with a large total_entries means your filter is narrow, not that the paper is sparse.

- not_found means the DOI is absent from the KG; not_matched means the DOI exists but has no discusses edge (4 such publications exist — the `no_discusses` bucket of list_publications). Both buckets are flat lists of DOIs — see docs://guide/conventions for the not_found / not_matched semantics. DOI matching is case-insensitive.

```mistake
discussed_by_publication(publication_dois=['10.1038/ismej.2016.70'])  # to get DE results for the paper
```

```correction
list_experiments(publication_dois=['10.1038/ismej.2016.70']) then differential_expression_by_gene(experiment_ids=[...])  # discusses edges are prose mentions, not expression data
```

## Package import equivalent

```python
from multiomics_explorer import discussed_by_publication

result = discussed_by_publication(publication_dois=...)
# returns dict with keys: total_entries, total_matching, returned, offset, truncated, by_entity_kind, by_prominence, top_kegg_pathways, top_publications, not_found, not_matched, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
