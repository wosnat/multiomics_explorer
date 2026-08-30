# search_ontology

## What it does

Search or browse ontology terms — Lucene over term names (search) or a gene_count-sorted listing (browse). Counts (`gene_count`, `organism_gene_count`, `min_gene_count`) are subtree-scoped; only the text match ignores hierarchy.

Returns term IDs and `level` for use with `genes_by_ontology`. With
`search_text`, supports fuzzy (~), wildcards (*), exact phrases ("..."),
boolean (AND, OR) — see docs://guide/conventions for syntax + scoring.
Without `search_text` (browse), rows sort by `gene_count DESC`; narrow
with `level`, `tree`/`interpro_type`, `min_gene_count`, `organism`.

`ontology` accepts one key, a list, or None (all 17). `limit`/`offset`
apply PER ontology (lockstep paging); rows are grouped by ontology in
registry order, then score DESC (search) / gene_count DESC (browse).
`by_ontology` carries per-ontology truncation.

[TRUST] `interpro_type` scopes InterPro terms to one entry type.
`informative_only` (default False) drops terms the KG flags
uninformative — e.g. KEGG KO 'uncharacterized protein' terms, GO root
go:0008150, KEGG global/overview maps like ko01100; term-side only,
never restricts the gene set. See docs://analysis/annotation_evidence
for the full trust surface, and docs://ontologies/{key} for what each
ontology means and how to read it.

Routing: chain term_ids into `genes_by_ontology` for gene discovery;
`ontology_term_details(term_ids=[...])` for a term's hierarchy, bridges
and per-organism counts; `docs://ontologies/index` for the per-ontology
reference.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Lucene query over term names, e.g. 'replication', 'oxido*', 'transport AND membrane'. None/'' = browse mode: list terms sorted by gene_count DESC (score null). See docs://guide/conventions for Lucene scoring. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') \| list[string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops')] \| None | None | Ontology key or list. None = all 17. limit/offset apply per ontology. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |
| level | int \| None | None | Hierarchy level filter (0 = broadest). See docs://guide/conventions for the level convention. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Applies to 'brite' only; raises if 'brite' is not in the ontology set. See docs://guide/conventions for the BRITE-tree scoping rule. |
| informative_only | bool | False | True drops terms the KG flags uninformative (roots, catch-alls). |
| verbose | bool | False | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type. Applies to 'interpro' only; raises if 'interpro' is not in the set. |
| min_gene_count | int \| None | None | Keep terms with gene_count >= this (subtree organism_gene_count when `organism` is set). Narrows browse mode. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
mode, total_entries, total_matching, score_max, score_median, returned, offset, truncated, by_ontology, by_level, by_interpro_type, by_family_type, skipped_ontologies, warnings, results
```

- **mode** (string ('search', 'browse')): 'search' (Lucene over search_text) or 'browse' (no search_text; sorted by gene_count).
- **total_entries** (int): Total terms in the selected ontologies (e.g. 847; summed over the set)
- **total_matching** (int): Terms matching the search (e.g. 31; summed over the set)
- **score_max** (float | None): Highest relevance score (null if 0 matches or browse, e.g. 5.23)
- **score_median** (float | None): Median relevance score (null if 0 matches or browse). Single ontology: over the full match; multi-ontology: over the returned page only.
- **returned** (int): Results in this response (0 when summary=true; <= limit x n_ontologies)
- **offset** (int): Offset into each ontology's result set (lockstep paging, e.g. 0)
- **truncated** (bool): True if any selected ontology has more matches than returned
- **by_ontology** (list[SearchOntologyByOntology]): Per-ontology totals + truncation flags, in ONTOLOGY_CONFIG order.
- **by_level** (list[SearchOntologyLevelBreakdown]): Terms per hierarchy level over the full match (browse mode, single ontology only — [] on multi-ontology browse because level scales differ).
- **by_interpro_type** (list[SearchOntologyInterproTypeBreakdown]): Matching InterPro terms per entry type (only when 'interpro' is in the set).
- **by_family_type** (list[SearchOntologyFamilyTypeBreakdown]): Matching NCBIfam terms per family type (only when 'ncbifam' is in the set).
- **skipped_ontologies** (list[object]): [{ontology, reason}] for ontologies in the set skipped because a filter does not apply to them.
- **warnings** (list[string]): Auto-warnings, e.g. browse truncated with no narrowing filter.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| id | string | Term ID (e.g. 'go:0006260') |
| name | string | Term name (e.g. 'DNA replication') |
| ontology_type | string \| None (optional) | Ontology key this row came from (e.g. 'go_bp', 'tcdb'); set on every compact row, single- or multi-ontology. |
| score | float \| None (optional) | Fulltext relevance score (e.g. 5.23); null in browse mode (no search_text). |
| level | int | Hierarchy level of this term (0 = broadest) |
| is_informative | bool | True iff term is not flagged is_uninformative (positive framing; coerced from sparse '<term>.is_uninformative' KG flag) |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| interpro_type | string \| None (optional) | InterPro entry type (sparse: interpro only), e.g. 'DOMAIN', 'FAMILY', 'HOMOLOGOUS_SUPERFAMILY'. |
| discussed_by_n_publications | int \| None (optional) | Publications that discuss this KEGG pathway in prose (KEGG only; None on other ontologies). Recall-biased narrative mention, NOT gene annotation. When > 0, set verbose=True for the per-paper DOI list, or call discussed_by_publication. |
| gene_count | int \| None (optional) | Subtree gene count on this term (precomputed Node.gene_count; sparse until every ontology's builder emits it). |
| organism_count | int \| None (optional) | Distinct organisms reaching this term (precomputed Node.organism_count; sparse until every ontology's builder emits it). |
| organism_gene_count | int \| None (optional) | Genes of `organism` in the term's SUBTREE (term + descendants; same scope as gene_count and as ontology_term_details.organism_gene_count); only when organism is set; browse sorts by it. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| discussed_in_publications | list[DiscussedPublicationRef] \| None (optional) | Per-paper {doi, prominence, evidence} for papers discussing this KEGG pathway (verbose-only; KEGG only). Call discussed_by_publication for a paper's full discussed set. |
| description | string \| None (optional) | Term description / definition (verbose only; sparse). |
| level_kind | string \| None (optional) | What `level` measures for this ontology, e.g. 'depth', 'tc_family' (verbose only). |
| direct_gene_count | int \| None (optional) | Genes annotated directly to this term, excluding descendants (verbose only; hierarchical ontologies). |
| superfamily | string \| None (optional) | TCDB superfamily label (verbose only; sparse: tcdb). |
| metabolite_count | int \| None (optional) | Distinct substrate metabolites attached to this TCDB family (verbose only; sparse: tcdb). |
| family_type | string \| None (optional) | NCBIfam family type, e.g. 'equivalog', 'subfamily' (verbose only; sparse: ncbifam). |
| gene_symbol | string \| None (optional) | NCBIfam gene symbol (verbose only; sparse: ncbifam). |
| family_class | string \| None (optional) | MEROPS family class ('peptidase' or 'inhibitor'; verbose only; sparse: merops). |
| catalytic_type | string \| None (optional) | MEROPS catalytic type, e.g. 'serine', 'metallo' (verbose only; sparse: merops). |
| peptidase_gene_count | int \| None (optional) | Genes with a 'peptidase' call_class on this MEROPS family (verbose only; sparse: merops). |

## Few-shot examples

### Example 1: Search GO biological processes

```example-call
search_ontology(search_text="replication", ontology=["go_bp"])
```

```example-response
{
  "mode": "search",
  "total_entries": 3433,
  "total_matching": 31,
  "score_max": 2.681756019592285,
  "score_median": 1.93581223487854,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "go_bp",
      "total_entries": 3433,
      "total_matching": 31,
      "score_max": 2.681756019592285,
      "returned": 5,
      "truncated": true
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "go:0006260",
      "name": "DNA replication",
      "ontology_type": "go_bp",
      "score": 2.681756019592285,
      "level": 6,
      "is_informative": true,
      "gene_count": 1340,
      "organism_count": 43
    },
    {
      "id": "go:0006270",
      "name": "DNA replication initiation",
      "ontology_type": "go_bp",
      "score": 2.3765029907226562,
      "level": 6,
      "is_informative": true,
      "gene_count": 124,
      "organism_count": 43
    },
    {
      "id": "go:0006274",
      "name": "DNA replication termination",
      "ontology_type": "go_bp",
      "score": 2.3765029907226562,
      "level": 6,
      "is_informative": true,
      "gene_count": 7,
      "organism_count": 6
    },
    ...
  ]
}
```

### Example 2: Browse mode — MEROPS families ranked by size (no search_text)

```example-call
search_ontology(ontology=["merops"], level=1)
```

```example-response
{
  "mode": "browse",
  "total_entries": 155,
  "total_matching": 97,
  "score_max": null,
  "score_median": null,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "merops",
      "total_entries": 155,
      "total_matching": 97,
      "score_max": null,
      "returned": 5,
      "truncated": true
    }
  ],
  "by_level": [{"level": 1, "count": 97}],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "merops.family:S33",
      "name": "prolyl aminopeptidase",
      "ontology_type": "merops",
      "score": null,
      "level": 1,
      "is_informative": true,
      "gene_count": 417,
      "organism_count": 43
    },
    {
      "id": "merops.family:S09",
      "name": "prolyl oligopeptidase",
      "ontology_type": "merops",
      "score": null,
      "level": 1,
      "is_informative": true,
      "gene_count": 300,
      "organism_count": 43
    },
    {
      "id": "merops.family:C26",
      "name": "gamma-glutamyl hydrolase",
      "ontology_type": "merops",
      "score": null,
      "level": 1,
      "is_informative": true,
      "gene_count": 278,
      "organism_count": 43
    },
    ...
  ]
}
```

### Example 3: Browse per organism — which TCDB families are biggest in MED4

```example-call
search_ontology(ontology=["tcdb"], level=2, organism="MED4", min_gene_count=5)
```

*organism= scopes the count: rows gain organism_gene_count, and the sort and min_gene_count apply to it (gene_count stays KG-wide). 'MED4' resolves to 'Prochlorococcus MED4'. organism_gene_count is subtree-scoped (term + descendants), the same number ontology_term_details(organism=...) reports — tcdb:3.A.1 in MED4 reads 65 on both tools.*

```example-response
{
  "mode": "browse",
  "total_entries": 1515,
  "total_matching": 22,
  "score_max": null,
  "score_median": null,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "tcdb",
      "total_entries": 1515,
      "total_matching": 22,
      "score_max": null,
      "returned": 5,
      "truncated": true
    }
  ],
  "by_level": [{"level": 2, "count": 22}],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "tcdb:3.A.1",
      "name": "The ATP-binding Cassette (ABC) Superfamily",
      "ontology_type": "tcdb",
      "score": null,
      "level": 2,
      "is_informative": true,
      "gene_count": 4900,
      "organism_count": 43,
      "organism_gene_count": 65
    },
    {
      "id": "tcdb:3.D.1",
      "name": "The H+ or Na+-translocating NADH Dehydrogenase (NDH) Family",
      "ontology_type": "tcdb",
      "score": null,
      "level": 2,
      "is_informative": true,
      "gene_count": 894,
      "organism_count": 43,
      "organism_gene_count": 20
    },
    {
      "id": "tcdb:3.A.9",
      "name": "The Chloroplast Envelope Protein Translocase (CEPT or Tic-Toc) Family",
      "ontology_type": "tcdb",
      "score": null,
      "level": 2,
      "is_informative": true,
      "gene_count": 663,
      "organism_count": 43,
      "organism_gene_count": 17
    },
    ...
  ]
}
```

### Example 4: Browse with no narrowing filter — the truncation auto-warning

```example-call
search_ontology(ontology=["go_bp"], limit=3)
```

*A browse that truncates with no `level` / facet / `min_gene_count` / `organism` filter is paging through a whole ontology; the envelope says so in `warnings`. `by_level` (browse only) is computed over the full match, so it tells you which level to narrow to.*

```example-response
{
  "mode": "browse",
  "total_entries": 3433,
  "total_matching": 3433,
  "score_max": null,
  "score_median": null,
  "returned": 3,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "go_bp",
      "total_entries": 3433,
      "total_matching": 3433,
      "score_max": null,
      "returned": 3,
      "truncated": true
    }
  ],
  "by_level": [
    {"level": 0, "count": 1},
    {"level": 1, "count": 16},
    {"level": 2, "count": 111},
    {"level": 3, "count": 324},
    {"level": 4, "count": 670},
    ...
  ],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [
    "Browse mode truncated with no narrowing filter — set level, min_gene_count, organism or a facet (tree / interpro_type..."
  ],
  "results": [
    {
      "id": "go:0008150",
      "name": "biological_process",
      "ontology_type": "go_bp",
      "score": null,
      "level": 0,
      "is_informative": false,
      "gene_count": 67696,
      "organism_count": 43
    },
    {
      "id": "go:0009987",
      "name": "cellular process",
      "ontology_type": "go_bp",
      "score": null,
      "level": 1,
      "is_informative": true,
      "gene_count": 61414,
      "organism_count": 43
    },
    {
      "id": "go:0008152",
      "name": "metabolic process",
      "ontology_type": "go_bp",
      "score": null,
      "level": 2,
      "is_informative": true,
      "gene_count": 48832,
      "organism_count": 43
    }
  ]
}
```

### Example 5: Browse several ontologies at once — by_level is empty on multi-ontology calls

```example-call
search_ontology(ontology=["merops", "ncbifam"], level=0, limit=3)
```

*Multi-ontology browse pages in lockstep (up to `limit` rows per ontology, rows grouped by ontology). `by_level` is only filled on a single-ontology browse — with two or more ontologies it comes back `[]` because levels mean different things per ontology; read `by_ontology[]` instead.*

```example-response
{
  "mode": "browse",
  "total_entries": 5112,
  "total_matching": 4998,
  "score_max": null,
  "score_median": null,
  "returned": 6,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "ncbifam",
      "total_entries": 4957,
      "total_matching": 4957,
      "score_max": null,
      "returned": 3,
      "truncated": true
    },
    {
      "ontology": "merops",
      "total_entries": 155,
      "total_matching": 41,
      "score_max": null,
      "returned": 3,
      "truncated": true
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "ncbifam:TIGR00254",
      "name": "diguanylate cyclase",
      "ontology_type": "ncbifam",
      "score": null,
      "level": 0,
      "is_informative": true,
      "gene_count": 696,
      "organism_count": 20
    },
    {
      "id": "ncbifam:TIGR00231",
      "name": "GTP-binding protein",
      "ontology_type": "ncbifam",
      "score": null,
      "level": 0,
      "is_informative": true,
      "gene_count": 475,
      "organism_count": 43
    },
    {
      "id": "ncbifam:TIGR00229",
      "name": "PAS domain S-box protein",
      "ontology_type": "ncbifam",
      "score": null,
      "level": 0,
      "is_informative": true,
      "gene_count": 403,
      "organism_count": 32
    },
    ...
  ]
}
```

### Example 6: One keyword across several ontologies (lockstep paging)

```example-call
search_ontology(search_text="transport", ontology=["go_bp", "tcdb"], limit=5)
```

```example-response
{
  "mode": "search",
  "total_entries": 4948,
  "total_matching": 366,
  "score_max": 3.75053071975708,
  "score_median": 2.0627857446670532,
  "returned": 10,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "go_bp",
      "total_entries": 3433,
      "total_matching": 324,
      "score_max": 1.5473122596740723,
      "returned": 5,
      "truncated": true
    },
    {
      "ontology": "tcdb",
      "total_entries": 1515,
      "total_matching": 42,
      "score_max": 3.75053071975708,
      "returned": 5,
      "truncated": true
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "go:0006810",
      "name": "transport",
      "ontology_type": "go_bp",
      "score": 1.5473122596740723,
      "level": 3,
      "is_informative": true,
      "gene_count": 10984,
      "organism_count": 43
    },
    {
      "id": "go:0015990",
      "name": "electron transport coupled proton transport",
      "ontology_type": "go_bp",
      "score": 1.3782250881195068,
      "level": 7,
      "is_informative": true,
      "gene_count": 155,
      "organism_count": 43
    },
    {
      "id": "go:0006821",
      "name": "chloride transport",
      "ontology_type": "go_bp",
      "score": 1.3485655784606934,
      "level": 5,
      "is_informative": true,
      "gene_count": 57,
      "organism_count": 43
    },
    ...
  ]
}
```

### Example 7: Search every ontology at once (ontology omitted)

```example-call
search_ontology(search_text="nitrate", limit=2)
```

```example-response
{
  "mode": "search",
  "total_entries": 49144,
  "total_matching": 155,
  "score_max": 7.6005682945251465,
  "score_median": 3.41845965385437,
  "returned": 19,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "go_bp",
      "total_entries": 3433,
      "total_matching": 6,
      "score_max": 3.5838801860809326,
      "returned": 2,
      "truncated": true
    },
    {
      "ontology": "go_mf",
      "total_entries": 2899,
      "total_matching": 6,
      "score_max": 3.2372517585754395,
      "returned": 2,
      "truncated": true
    },
    {
      "ontology": "go_cc",
      "total_entries": 451,
      "total_matching": 1,
      "score_max": 2.6981472969055176,
      "returned": 1,
      "truncated": false
    },
    {
      "ontology": "ec",
      "total_entries": 7337,
      "total_matching": 7,
      "score_max": 3.41845965385437,
      "returned": 2,
      "truncated": true
    },
    {
      "ontology": "kegg",
      "total_entries": 5143,
      "total_matching": 20,
      "score_max": 2.7984232902526855,
      "returned": 2,
      "truncated": true
    },
    ...
  ],
  "by_level": [],
  "by_interpro_type": [{"interpro_type": "FAMILY", "count": 2}],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "go:0042128",
      "name": "nitrate assimilation",
      "ontology_type": "go_bp",
      "score": 3.5838801860809326,
      "level": 4,
      "is_informative": true,
      "gene_count": 88,
      "organism_count": 32
    },
    {
      "id": "go:1902025",
      "name": "nitrate import",
      "ontology_type": "go_bp",
      "score": 3.5838801860809326,
      "level": 5,
      "is_informative": true,
      "gene_count": 54,
      "organism_count": 25
    },
    {
      "id": "go:0008940",
      "name": "nitrate reductase activity",
      "ontology_type": "go_mf",
      "score": 3.2372517585754395,
      "level": 4,
      "is_informative": true,
      "gene_count": 23,
      "organism_count": 10
    },
    ...
  ]
}
```

### Example 8: Summary only (how many terms match?)

```example-call
search_ontology(search_text="transport", ontology=["go_bp"], summary=True)
```

### Example 9: BRITE search scoped to a specific tree

```example-call
search_ontology(search_text="transport", ontology=["brite"], tree="transporters")
```

```example-response
{
  "mode": "search",
  "total_entries": 2681,
  "total_matching": 2,
  "score_max": 2.494616985321045,
  "score_median": 2.1319267749786377,
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "by_ontology": [
    {
      "ontology": "brite",
      "total_entries": 2681,
      "total_matching": 2,
      "score_max": 2.494616985321045,
      "returned": 2,
      "truncated": false
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "kegg.brite:ko02000.A2.B2.C3",
      "name": "Arabinogalactan oligomer/maltooligosaccharide transport system",
      "ontology_type": "brite",
      "score": 2.494616985321045,
      "level": 2,
      "is_informative": true,
      "tree": "transporters",
      "tree_code": "ko02000",
      "gene_count": 37,
      "organism_count": 17
    },
    {
      "id": "kegg.brite:ko02000.A6.B6",
      "name": "Accessory factors involved in transport [TC:8]",
      "ontology_type": "brite",
      "score": 2.1319267749786377,
      "level": 1,
      "is_informative": true,
      "tree": "transporters",
      "tree_code": "ko02000",
      "gene_count": 215,
      "organism_count": 23
    }
  ]
}
```

### Example 10: Filter search results by hierarchy level

```example-call
search_ontology(search_text="oxido*", ontology=["kegg"], level=2)
```

### Example 11: Find TCDB families that move sucrose

```example-call
search_ontology(search_text="sucrose", ontology=["tcdb"])
```

```example-response
{
  "mode": "search",
  "total_entries": 1515,
  "total_matching": 6,
  "score_max": 6.737510681152344,
  "score_median": 3.3274388313293457,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "tcdb",
      "total_entries": 1515,
      "total_matching": 6,
      "score_max": 6.737510681152344,
      "returned": 5,
      "truncated": true
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "tcdb:3.A.1.1.8",
      "name": "Sucrose/maltose/trehalose porter (sucrose-inducible)",
      "ontology_type": "tcdb",
      "score": 6.737510681152344,
      "level": 4,
      "is_informative": true,
      "gene_count": 3,
      "organism_count": 1
    },
    {
      "id": "tcdb:3.A.1.1.17",
      "name": "Trehalose/maltose/sucrose porter (trehalose inducible)",
      "ontology_type": "tcdb",
      "score": 5.250369548797607,
      "level": 4,
      "is_informative": true,
      "gene_count": 3,
      "organism_count": 1
    },
    {
      "id": "tcdb:1.B.3.1.2",
      "name": "Oligosaccharide porin, ScrY (transports sucrose, raffinose and maltooligo-saccharides).",
      "ontology_type": "tcdb",
      "score": 4.501997947692871,
      "level": 4,
      "is_informative": true,
      "gene_count": 1,
      "organism_count": 1
    },
    ...
  ]
}
```

### Example 12: Search InterPro entries, scoped to one interpro_type

```example-call
search_ontology(search_text="P-loop", ontology=["interpro"], interpro_type="HOMOLOGOUS_SUPERFAMILY")
```

```example-response
{
  "mode": "search",
  "total_entries": 13000,
  "total_matching": 49,
  "score_max": 9.800861358642578,
  "score_median": 1.573620319366455,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "interpro",
      "total_entries": 13000,
      "total_matching": 49,
      "score_max": 9.800861358642578,
      "returned": 5,
      "truncated": true
    }
  ],
  "by_level": [],
  "by_interpro_type": [{"interpro_type": "HOMOLOGOUS_SUPERFAMILY", "count": 5}],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "interpro:IPR027417",
      "name": "P-loop containing nucleoside triphosphate hydrolase",
      "ontology_type": "interpro",
      "score": 9.800861358642578,
      "level": 0,
      "is_informative": true,
      "interpro_type": "HOMOLOGOUS_SUPERFAMILY",
      "gene_count": 7045,
      "organism_count": 43
    },
    {
      "id": "interpro:IPR008250",
      "name": "P-type ATPase, A domain superfamily",
      "ontology_type": "interpro",
      "score": 5.831203460693359,
      "level": 0,
      "is_informative": true,
      "interpro_type": "HOMOLOGOUS_SUPERFAMILY",
      "gene_count": 94,
      "organism_count": 42
    },
    {
      "id": "interpro:IPR023534",
      "name": "Rof/RNase P-like",
      "ontology_type": "interpro",
      "score": 4.432365417480469,
      "level": 0,
      "is_informative": true,
      "interpro_type": "HOMOLOGOUS_SUPERFAMILY",
      "gene_count": 7,
      "organism_count": 7
    },
    ...
  ]
}
```

### Example 13: Browse NCBIfam families with their family_type (verbose)

```example-call
search_ontology(ontology=["ncbifam"], min_gene_count=300, verbose=True)
```

```example-response
{
  "mode": "browse",
  "total_entries": 4957,
  "total_matching": 4,
  "score_max": null,
  "score_median": null,
  "returned": 4,
  "offset": 0,
  "truncated": false,
  "by_ontology": [
    {
      "ontology": "ncbifam",
      "total_entries": 4957,
      "total_matching": 4,
      "score_max": null,
      "returned": 4,
      "truncated": false
    }
  ],
  "by_level": [{"level": 0, "count": 4}],
  "by_interpro_type": [],
  "by_family_type": [{"family_type": "domain", "count": 3}, {"family_type": "superfamily", "count": 1}],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "ncbifam:TIGR00254",
      "name": "diguanylate cyclase",
      "ontology_type": "ncbifam",
      "score": null,
      "level": 0,
      "is_informative": true,
      "gene_count": 696,
      "organism_count": 20,
      "description": "The GGDEF domain is named for the motif GG[DE]EF shared by many proteins carrying the domain. There is evidence that ...",
      "level_kind": null,
      "family_type": "domain",
      "gene_symbol": null
    },
    {
      "id": "ncbifam:TIGR00231",
      "name": "GTP-binding protein",
      "ontology_type": "ncbifam",
      "score": null,
      "level": 0,
      "is_informative": true,
      "gene_count": 475,
      "organism_count": 43,
      "description": "Proteins with a small GTP-binding domain recognized by this model include Ras, RhoA, Rab11, translation elongation fa...",
      "level_kind": null,
      "family_type": "domain",
      "gene_symbol": null
    },
    {
      "id": "ncbifam:TIGR00229",
      "name": "PAS domain S-box protein",
      "ontology_type": "ncbifam",
      "score": null,
      "level": 0,
      "is_informative": true,
      "gene_count": 403,
      "organism_count": 32,
      "description": "The PAS domain was previously described. This sensory box, or S-box domain occupies the central portion of the PAS do...",
      "level_kind": null,
      "family_type": "domain",
      "gene_symbol": null
    },
    ...
  ]
}
```

### Example 14: Search MEROPS peptidase families

```example-call
search_ontology(search_text="serine protease", ontology=["merops"])
```

```example-response
{
  "mode": "search",
  "total_entries": 155,
  "total_matching": 19,
  "score_max": 1.636549949645996,
  "score_median": 0.5249618291854858,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "merops",
      "total_entries": 155,
      "total_matching": 19,
      "score_max": 1.636549949645996,
      "returned": 5,
      "truncated": true
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "merops.family:M50",
      "name": "S2P protease",
      "ontology_type": "merops",
      "score": 1.636549949645996,
      "level": 1,
      "is_informative": true,
      "gene_count": 87,
      "organism_count": 43
    },
    {
      "id": "merops.family:S16",
      "name": "lon protease",
      "ontology_type": "merops",
      "score": 1.636549949645996,
      "level": 1,
      "is_informative": true,
      "gene_count": 82,
      "organism_count": 43
    },
    {
      "id": "merops.family:S49",
      "name": "protease IV",
      "ontology_type": "merops",
      "score": 1.636549949645996,
      "level": 1,
      "is_informative": true,
      "gene_count": 89,
      "organism_count": 43
    },
    ...
  ]
}
```

### Example 15: Find PSORTb subcellular localizations

```example-call
search_ontology(search_text="outer", ontology=["subcellular_localization"])
```

```example-response
{
  "mode": "search",
  "total_entries": 5,
  "total_matching": 1,
  "score_max": 0.5361359119415283,
  "score_median": 0.5361359119415283,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "by_ontology": [
    {
      "ontology": "subcellular_localization",
      "total_entries": 5,
      "total_matching": 1,
      "score_max": 0.5361359119415283,
      "returned": 1,
      "truncated": false
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "psortb_OuterMembrane",
      "name": "Outer membrane",
      "ontology_type": "subcellular_localization",
      "score": 0.5361359119415283,
      "level": 0,
      "is_informative": true,
      "gene_count": 2097,
      "organism_count": 43
    }
  ]
}
```

### Example 16: Filter out uninformative terms (term-side, opt-in)

```example-call
search_ontology(search_text="transport", ontology=["kegg"], informative_only=True)
```

*informative_only=True drops terms flagged is_uninformative='true' (KEGG KOs named 'uncharacterized protein' — KO level only, pathway maps are never flagged; a few Cyanorak / TIGR / GO / COG roots; broad InterPro superfamilies and NCBIfam families). Each row carries is_informative. Use it when seeding term IDs into genes_by_ontology for enrichment. KO ids are `kegg.orthology:K…`.*

```example-response
{
  "mode": "search",
  "total_entries": 5143,
  "total_matching": 329,
  "score_max": 1.7505996227264404,
  "score_median": 1.155104637145996,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "by_ontology": [
    {
      "ontology": "kegg",
      "total_entries": 5143,
      "total_matching": 329,
      "score_max": 1.7505996227264404,
      "returned": 5,
      "truncated": true
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "kegg.subcategory:09131",
      "name": "Membrane transport",
      "ontology_type": "kegg",
      "score": 1.7505996227264404,
      "level": 1,
      "is_informative": true,
      "discussed_by_n_publications": 0,
      "gene_count": 3358,
      "organism_count": 43
    },
    {
      "id": "kegg.subcategory:09141",
      "name": "Transport and catabolism",
      "ontology_type": "kegg",
      "score": 1.6120857000350952,
      "level": 1,
      "is_informative": true,
      "discussed_by_n_publications": 0,
      "gene_count": 399,
      "organism_count": 43
    },
    {
      "id": "kegg.orthology:K06197",
      "name": "chaB; cation transport regulator",
      "ontology_type": "kegg",
      "score": 1.4938839673995972,
      "level": 3,
      "is_informative": true,
      "discussed_by_n_publications": 0,
      "gene_count": 1,
      "organism_count": 1
    },
    ...
  ]
}
```

### Example 17: Which papers discuss a KEGG pathway (literature index)

```example-call
search_ontology(search_text="calvin", ontology=["kegg"])
```

```example-response
{
  "mode": "search",
  "total_entries": 5143,
  "total_matching": 1,
  "score_max": 4.122867107391357,
  "score_median": 4.122867107391357,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "by_ontology": [
    {
      "ontology": "kegg",
      "total_entries": 5143,
      "total_matching": 1,
      "score_max": 4.122867107391357,
      "returned": 1,
      "truncated": false
    }
  ],
  "by_level": [],
  "by_interpro_type": [],
  "by_family_type": [],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {
      "id": "kegg.pathway:ko00710",
      "name": "Carbon fixation by Calvin cycle",
      "ontology_type": "kegg",
      "score": 4.122867107391357,
      "level": 2,
      "is_informative": true,
      "discussed_by_n_publications": 23,
      "gene_count": 714,
      "organism_count": 43
    }
  ]
}
```

### Example 18: From search to gene discovery

```
Step 1: search_ontology(search_text="replication", ontology=["go_bp"])
        → collect term IDs from results (e.g. "go:0006260")

Step 2: ontology_term_details(term_ids=["go:0006260"])
        → parents / children / gene_count per organism — confirm the term
          sits at the right granularity before expanding it

Step 3: genes_by_ontology(ontology="go_bp", organism="MED4", term_ids=["go:0006260"])
        → (gene × term) pairs in MED4 (hierarchy expansion DOWN)

Step 4: gene_overview(locus_tags=["PMM0845", ...])
        → data availability for the discovered genes
```

### Example 19: Browse → pick a level → enrich

```
Step 1: search_ontology(ontology=["cyanorak_role"], level=1, organism="MED4")
        → the level-1 roles ranked by MED4 gene count (no keyword needed)

Step 2: ontology_landscape(ontology=["cyanorak_role"], organism="MED4")
        → confirm level 1 has usable coverage / term sizes

Step 3: pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1)
```

## Chaining patterns

```
search_ontology → ontology_term_details(term_ids=[...]) — inspect the hits' parents / children / bridges before expanding
search_ontology → genes_by_ontology
search_ontology → genes_by_ontology → gene_overview
search_ontology(ontology=[key], level=N) (browse) → ontology_landscape(ontology=[key]) → pathway_enrichment(ontology=key, level=N)
list_filter_values('brite_tree') → search_ontology(ontology=['brite'], tree=...)
search_ontology(ontology=['kegg'], verbose=True) → read per-term discussed_in_publications DOIs → list_publications(publication_dois=[...]) or discussed_by_publication(publication_dois=[...])
search_ontology(ontology=['interpro'], interpro_type=...) / ['ncbifam'] / ['merops'] → genes_by_ontology(ontology=..., term_ids=[...], organism=...) — same forward chain as every other ontology
```

## Common mistakes

- search_ontology finds term IDs — use genes_by_ontology to find (gene × term) pairs annotated to those terms (single organism required, hierarchy expanded DOWN by default), and ontology_term_details for a term's parents / children / bridges. Neither search nor browse walks the hierarchy for you — but the counts they show (`gene_count`, `organism_gene_count`) are subtree-scoped on hierarchical ontologies.

- `ontology` is a list (a single string is accepted); omit it to fan out over all 17 in registry order. `limit` / `offset` apply PER ontology (lockstep paging — `returned <= limit x n`); read `by_ontology[].truncated` to see which ontology still has pages. See docs://guide/conventions.

- Browse mode (no `search_text`) sorts by `gene_count DESC, id` and leaves `score` null; a browse that truncates with no `level` / facet / `min_gene_count` / `organism` filter adds a warning — you are paging through a whole ontology. Narrow first.

- `organism=` (browse) changes what is sorted and filtered: rows gain `organism_gene_count`, `min_gene_count` applies to it, and `gene_count` stays KG-wide. Without `organism=`, `gene_count` / `organism_count` are counts across all organisms on the term node. The name resolves like every other tool (`'MED4'` → `'Prochlorococcus MED4'`; unknown or ambiguous raises).

- `organism_gene_count` is subtree-scoped (term + descendants, one organism; BRITE via its KEGG bridge) — the same scope as `gene_count` (all organisms) and the same number `ontology_term_details(organism=...)` reports (`tcdb:3.A.1` in MED4: 65 on both). A parent therefore never shows fewer genes than its child. For node-local counts read `direct_gene_count` (verbose, hierarchical labels only).

- `score_median` is over the full match on a single-ontology search, but over the RETURNED PAGE on multi-ontology calls (the per-ontology summaries carry no pooled median). `score_max` is exact in both cases.

- Lucene scores are per index: rows of two ontologies in one call are grouped by ontology, not interleaved by score. Never rank a `go_bp` row against a `tcdb` row by `score`.

- A facet (`tree` for BRITE, `interpro_type` for InterPro) narrows only its owner and raises when the owner is not in the ontology list. For BRITE, always pass `tree=` — without it the `enzymes` tree dominates. Discover trees via `list_filter_values('brite_tree')`.

- `interpro_type` scopes InterPro to one of the 8 types (`FAMILY`, `DOMAIN`, `HOMOLOGOUS_SUPERFAMILY`, `REPEAT`, `CONSERVED_SITE`, `ACTIVE_SITE`, `BINDING_SITE`, `PTM`); the envelope's `by_interpro_type` (and `by_family_type` for NCBIfam) shows the mix when you don't.

- Supported ontologies: `go_bp`, `go_mf`, `go_cc`, `kegg`, `ec`, `cog_category`, `cyanorak_role`, `tigr_role`, `pfam`, `brite`, `tcdb`, `cazy`, `subcellular_localization`, `signal_peptide_type`, `interpro`, `ncbifam`, `merops`. Each has a reference page at docs://ontologies/{key} (identifier form, levels, what `gene_count` means there).

- Use `level` to restrict results to a hierarchy depth (0 = broadest). PSORTb, SignalP, COG and NCBIfam are flat — `level=1` returns nothing for them. Pfam clans are level 0, domains level 1. TIGR is two-level: level 0 = the 21 main roles (`level_kind='tigr_mainrole'`), level 1 = sub roles (`level_kind='tigr_subrole'`).

- TCDB is family-level transporter classification. For substrate-anchored questions ('which genes transport sucrose?'), chain via `genes_by_metabolite` instead — that tool surfaces the TCDB substrate edges directly.

- PSORTb / SignalP are structural ontologies (where a protein is / how it is handled), not functional — use them for localization / secretion questions.

- discussed_by_n_publications (how many papers name the pathway in prose) is present only for `kegg`. It is a recall-biased literature index, NOT DE-table expression. verbose=True adds the per-term {doi, prominence, evidence} list; route DOIs into discussed_by_publication.

- Use this to assemble a custom `term_ids=[...]` list for `pathway_enrichment` / `cluster_enrichment` when relevant terms live at different depths (GO is graph-shaped). See docs://analysis/enrichment.

```mistake
search_ontology(search_text='PMM0845', ontology=['go_bp'])  # searching for a gene
```

```correction
resolve_gene(identifier='PMM0845')  # use resolve_gene for gene lookups
```

```mistake
search_ontology(search_text='*', ontology=['merops'])  # trying to list everything
```

```correction
search_ontology(ontology=['merops'], level=1)  # browse mode: omit search_text, narrow with level
```

## Package import equivalent

```python
from multiomics_explorer import search_ontology

result = search_ontology()
# returns dict with keys: mode, total_entries, total_matching, score_max, score_median, returned, offset, truncated, by_ontology, by_level, by_interpro_type, by_family_type, skipped_ontologies, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
