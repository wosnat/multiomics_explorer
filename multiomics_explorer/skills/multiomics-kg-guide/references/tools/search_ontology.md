# search_ontology

## What it does

Search or browse ontology terms — Lucene over term names (search) or a gene_count-sorted listing (browse); no hierarchy traversal.

Returns term IDs and `level` for use with `genes_by_ontology`. With
`search_text`, supports fuzzy (~), wildcards (*), exact phrases ("..."),
boolean (AND, OR) — see docs://guide/conventions for syntax + scoring.
Without `search_text` (browse), rows sort by `gene_count DESC`; narrow
with `level`, `tree`/`interpro_type`, `min_gene_count`, `organism`.

`ontology` accepts one key, a list, or None (all 17). `limit`/`offset`
apply PER ontology (lockstep paging); rows are grouped by ontology in
registry order, then score DESC (search) / gene_count DESC (browse).
`by_ontology` carries per-ontology truncation.

[TRUST] `interpro_type` scopes InterPro terms to one entry type. See
docs://analysis/annotation_evidence for the full trust surface, and
docs://ontologies/{key} for what each ontology means and how to read it.

Routing: chain term_ids into `genes_by_ontology` for gene discovery;
`ontology_term_details(term_ids=[...])` for a term's hierarchy, bridges
and per-organism counts; `docs://ontologies/index` for the per-ontology
reference.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Lucene query over term names, e.g. 'replication', 'oxido*', 'transport AND membrane'. None/'' = browse mode: list terms sorted by gene_count DESC (score null). See docs://guide/conventions for Lucene scoring. |
| ontology | list[string] \| None | None | Ontology key or list: go_bp, go_mf, go_cc, kegg, ec, cog_category, cyanorak_role, tigr_role, pfam, brite, tcdb, cazy, subcellular_localization, signal_peptide_type, interpro, ncbifam, merops. None = all 17. limit/offset apply per ontology. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| limit | int | 5 | Max results per ontology (returned <= limit x n_ontologies). |
| offset | int | 0 | Number of results to skip per ontology (lockstep paging). |
| level | int \| None | None | Hierarchy level filter (0 = broadest). See docs://guide/conventions for the level convention. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Applies to 'brite' only; raises if 'brite' is not in the ontology set. See docs://guide/conventions for the BRITE-tree scoping rule. |
| informative_only | bool | False | When True, exclude terms flagged uninformative in KG (e.g. KEGG 'metabolic pathways' map00001, GO root 'biological_process' go:0008150). Term-side filter only — never restricts the gene set. Default False (opt-in). |
| verbose | bool | False | Add description, level_kind, direct_gene_count, per-ontology columns (tcdb superfamily/metabolite_count, ncbifam family_type/gene_symbol, merops family_class/catalytic_type/peptidase_gene_count) and KEGG discussed_in_publications. Default compact. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type. Applies to 'interpro' only; raises if 'interpro' is not in the set. |
| min_gene_count | int \| None | None | Keep terms with gene_count >= this (subtree organism_gene_count when `organism` is set). Narrows browse mode. |
| organism | string \| None | None | Organism to scope counts to (resolved like every other tool: 'MED4' -> 'Prochlorococcus MED4'; unknown/ambiguous raises). Rows gain organism_gene_count (direct edge) and browse sorts by it. |

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
  "total_entries": 2448,
  "total_matching": 31,
  "score_max": 2.48,
  "score_median": 1.78,
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "by_ontology": [{"ontology": "go_bp", "total_entries": 2448, "total_matching": 31, "score_max": 2.48, "returned": 5, "truncated": true}],
  "skipped_ontologies": [],
  "warnings": [],
  "results": [
    {"id": "go:0006260", "name": "DNA replication", "score": 2.48, "level": 4, "ontology_type": "go_bp", "gene_count": 1290, "organism_count": 42},
    {"id": "go:0006261", "name": "DNA-templated DNA replication", "score": 2.41, "level": 5, "ontology_type": "go_bp", "gene_count": 640, "organism_count": 42},
    ...
  ]
}
```

### Example 2: Browse mode — MEROPS families ranked by size (no search_text)

```example-call
search_ontology(ontology=["merops"], level=1)
```

```example-response
# Omit search_text to browse: every term of the ontology, sorted
# gene_count DESC then id, score null, envelope mode='browse' with
# by_level over the full match. level / min_gene_count / organism /
# informative_only / facets narrow it.
{
  "mode": "browse",
  "total_entries": 155,
  "total_matching": 97,
  "score_max": null,
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "by_level": [{"level": 1, "count": 97}],
  "by_ontology": [{"ontology": "merops", "total_entries": 155, "total_matching": 97, "score_max": null, "returned": 5, "truncated": true}],
  "warnings": [],
  "results": [
    {"id": "merops.family:S33", "name": "prolyl aminopeptidase", "score": null, "level": 1, "ontology_type": "merops", "gene_count": 412, "organism_count": 42},
    {"id": "merops.family:C44", "name": "glutamine-fructose-6-phosphate transaminase", "score": null, "level": 1, "ontology_type": "merops", "gene_count": 169, "organism_count": 42},
    ...
  ]
}
```

### Example 3: Browse per organism — which TCDB families are biggest in MED4

```example-call
search_ontology(ontology=["tcdb"], level=2, organism="MED4", min_gene_count=5)
```

```example-response
# organism= scopes the count: rows gain organism_gene_count, the sort
# and min_gene_count apply to it (gene_count stays KG-wide). 'MED4'
# resolves to 'Prochlorococcus MED4'. organism_gene_count is the DIRECT
# gene edge (57 here); ontology_term_details gives the subtree count (65).
{"mode": "browse", "total_matching": 16, "results": [
  {"id": "tcdb:3.A.1", "name": "ATP-binding Cassette (ABC) Superfamily", "score": null, "level": 2, "ontology_type": "tcdb", "gene_count": 4817, "organism_count": 42, "organism_gene_count": 57},
  ...
]}
```

### Example 4: One keyword across several ontologies (lockstep paging)

```example-call
search_ontology(search_text="transport", ontology=["go_bp", "tcdb"], limit=5)
```

```example-response
# limit / offset apply PER ontology: up to 5 go_bp rows then up to 5
# tcdb rows (returned <= limit x n). Flat keys are sums / max across the
# set; by_ontology carries the per-ontology truncation flags. Lucene
# scores are per index — never rank a go_bp row against a tcdb row.
{
  "mode": "search",
  "total_matching": 412,
  "returned": 10,
  "truncated": true,
  "by_ontology": [
    {"ontology": "go_bp", "total_entries": 2448, "total_matching": 260, "score_max": 3.9, "returned": 5, "truncated": true},
    {"ontology": "tcdb", "total_entries": 1515, "total_matching": 152, "score_max": 3.1, "returned": 5, "truncated": true}
  ],
  "results": [
    {"id": "go:0006810", "name": "transport", "score": 3.9, "level": 3, "ontology_type": "go_bp", "gene_count": 15838, "organism_count": 42},
    ...,
    {"id": "tcdb:3", "name": "Primary Active Transporters", "score": 3.1, "level": 0, "ontology_type": "tcdb", "gene_count": 12580, "organism_count": 42},
    ...
  ]
}
```

### Example 5: Search every ontology at once (ontology omitted)

```example-call
search_ontology(search_text="nitrate", limit=2)
```

```example-response
# ontology=None fans out over all 17 in registry order, 2 rows each at
# most; ontologies with no hit contribute a by_ontology entry with
# total_matching 0 and no rows.
{"mode": "search", "returned": 14, "by_ontology": [{"ontology": "go_bp", "total_matching": 9, "returned": 2, "truncated": true}, "..."],
 "results": [{"id": "go:0042128", "name": "nitrate assimilation", "ontology_type": "go_bp", "score": 3.4, "level": 5, "gene_count": 233, "organism_count": 44}, "..."]}
```

### Example 6: Summary only (how many terms match?)

```example-call
search_ontology(search_text="transport", ontology=["go_bp"], summary=True)
```

### Example 7: BRITE search scoped to a specific tree

```example-call
search_ontology(search_text="transport", ontology=["brite"], tree="transporters")
```

```example-response
{
  "mode": "search",
  "total_entries": 84,
  "total_matching": 12,
  "score_max": 3.1,
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "results": [
    {"id": "kegg.brite:ko02000.A2", "name": "ABC transporters", "score": 3.1, "level": 1, "ontology_type": "brite", "tree": "transporters", "tree_code": "ko02000", "gene_count": 2210, "organism_count": 42},
    ...
  ]
}
```

### Example 8: Filter search results by hierarchy level

```example-call
search_ontology(search_text="oxido*", ontology=["kegg"], level=2)
```

### Example 9: Find TCDB families that move sucrose

```example-call
search_ontology(search_text="sucrose", ontology=["tcdb"])
```

```example-response
{
  "mode": "search",
  "total_matching": 6,
  "score_max": 3.42,
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "results": [
    {"id": "tcdb:2.A.1.5.3", "name": "Sucrose:H+ symporter", "score": 3.42, "level": 4, "ontology_type": "tcdb", "gene_count": 3, "organism_count": 2},
    ...
  ]
}
```

### Example 10: Search InterPro entries, scoped to one interpro_type

```example-call
search_ontology(search_text="P-loop", ontology=["interpro"], interpro_type="HOMOLOGOUS_SUPERFAMILY")
```

```example-response
# interpro_type scopes InterPro the way tree scopes BRITE — omit it and
# results mix all 8 InterPro types, which size very differently. The
# envelope adds by_interpro_type whenever interpro is in the set.
{"mode": "search", "total_matching": 3, "by_interpro_type": [{"interpro_type": "HOMOLOGOUS_SUPERFAMILY", "count": 3}],
 "results": [
   {"id": "interpro:IPR027417", "name": "P-loop containing nucleoside triphosphate hydrolase", "score": 2.9, "level": 0, "ontology_type": "interpro", "interpro_type": "HOMOLOGOUS_SUPERFAMILY", "gene_count": 6909, "organism_count": 42}
 ]}
```

### Example 11: Browse NCBIfam families with their family_type (verbose)

```example-call
search_ontology(ontology=["ncbifam"], min_gene_count=300, verbose=True)
```

```example-response
# verbose adds description, level_kind, direct_gene_count (hierarchical
# labels only) and the ontology's term-level extras — ncbifam
# family_type + gene_symbol, tcdb superfamily + metabolite_count,
# merops family_class + catalytic_type + peptidase_gene_count.
{"mode": "browse", "by_family_type": [{"family_type": "equivalog", "count": 4}, {"family_type": "subfamily", "count": 2}],
 "results": [
   {"id": "ncbifam:TIGR00254", "name": "diguanylate cyclase", "score": null, "level": 0, "ontology_type": "ncbifam", "gene_count": 696, "organism_count": 20,
    "description": "...", "family_type": "subfamily", "gene_symbol": null}
 ]}
```

### Example 12: Search MEROPS peptidase families

```example-call
search_ontology(search_text="serine protease", ontology=["merops"])
```

```example-response
{"mode": "search", "total_matching": 8, "results": [
  {"id": "merops.family:S14", "name": "Clp protease", "score": 3.0, "level": 1, "ontology_type": "merops", "gene_count": 125, "organism_count": 41}
]}
```

### Example 13: Find PSORTb subcellular localizations

```example-call
search_ontology(search_text="outer", ontology=["subcellular_localization"])
```

```example-response
{
  "mode": "search",
  "total_entries": 5,
  "total_matching": 1,
  "returned": 1,
  "truncated": false,
  "offset": 0,
  "results": [
    {"id": "psortb_OuterMembrane", "name": "Outer membrane", "score": 2.42, "level": 0, "ontology_type": "subcellular_localization", "gene_count": 2087, "organism_count": 42}
  ]
}
```

### Example 14: Filter out uninformative terms (term-side, opt-in)

```example-call
search_ontology(search_text="transport", ontology=["kegg"], informative_only=True)
```

```example-response
# informative_only=True drops terms flagged is_uninformative='true'
# (catch-all KEGG maps and KO groups, a few Cyanorak / TIGR / GO / COG
# entries, broad InterPro superfamilies, broad NCBIfam families). Each
# row carries is_informative. Use it when seeding term IDs into
# genes_by_ontology for enrichment.
{"mode": "search", "total_matching": 22, "results": [
  {"id": "kegg:K02035", "name": "ABC.PE.S; peptide/nickel transport system substrate-binding protein", "score": 2.81, "level": 3, "ontology_type": "kegg", "is_informative": true, "gene_count": 304, "organism_count": 46}
]}
```

### Example 15: Which papers discuss a KEGG pathway (literature index)

```example-call
search_ontology(search_text="calvin", ontology=["kegg"])
```

```example-response
# KEGG terms carry discussed_by_n_publications — how many publications
# name the pathway in prose. Present ONLY for kegg; other ontologies
# omit it. verbose=True expands the {doi, prominence, evidence} list.
{"mode": "search", "total_matching": 3, "results": [
  {"id": "kegg.pathway:ko00710", "name": "Carbon fixation by Calvin cycle", "score": 3.2, "level": 2, "ontology_type": "kegg", "gene_count": 1210, "organism_count": 42, "discussed_by_n_publications": 19}
]}
```

### Example 16: From search to gene discovery

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

### Example 17: Browse → pick a level → enrich

```
Step 1: search_ontology(ontology=["cyanorak_role"], level=1, organism="MED4")
        → the level-1 roles ranked by MED4 gene count (no keyword needed)

Step 2: ontology_landscape(ontology=["cyanorak_role"], organism="MED4")
        → confirm level 1 has usable coverage / term sizes

Step 3: pathway_enrichment(organism="MED4", experiment_ids=["EXP042"], ontology="cyanorak_role", level=1)
```

## Chaining patterns

```
search_ontology → ontology_term_details(term_ids=[...]) — inspect the hits' parents / children / bridges before expanding
search_ontology → genes_by_ontology
search_ontology → genes_by_ontology → gene_overview
search_ontology(ontology=[key], level=N) (browse) → ontology_landscape(ontology=[key]) → pathway_enrichment(ontology=key, level=N)
list_filter_values('brite_tree') → search_ontology(ontology=['brite'], tree=...)
search_ontology(ontology=['kegg'], verbose=True) → read per-term discussed_in_publications DOIs → list_publications(publication_dois=[...]) or discussed_by_publication(publication_dois=[...])
search_ontology(ontology=['interpro'], interpro_type=...) / ['ncbifam'] / ['merops'] → genes_by_ontology(ontology=..., term_ids=[...], organism=...) — same forward chain as the other 14 ontologies
```

## Common mistakes

- search_ontology finds term IDs — use genes_by_ontology to find (gene × term) pairs annotated to those terms (single organism required, hierarchy expanded DOWN by default), and ontology_term_details for a term's parents / children / bridges. Neither search nor browse traverses the hierarchy.

- `ontology` is a list (a single string is accepted); omit it to fan out over all 17 in registry order. `limit` / `offset` apply PER ontology (lockstep paging — `returned <= limit x n`); read `by_ontology[].truncated` to see which ontology still has pages. See docs://guide/conventions.

- Browse mode (no `search_text`) sorts by `gene_count DESC, id` and leaves `score` null; a browse that truncates with no `level` / facet / `min_gene_count` / `organism` filter adds a warning — you are paging through a whole ontology. Narrow first.

- `organism=` (browse) changes what is sorted and filtered: rows gain `organism_gene_count`, `min_gene_count` applies to it, and `gene_count` stays KG-wide. Without `organism=`, `gene_count` / `organism_count` are counts across all organisms on the term node. The name resolves like every other tool (`'MED4'` → `'Prochlorococcus MED4'`; unknown or ambiguous raises).

- `organism_gene_count` is the term's DIRECT gene edge in that organism (BRITE via its KEGG bridge) — NOT the subtree. It differs from `gene_count` (subtree, all organisms) and from `ontology_term_details.organism_gene_count` (subtree, one organism). On hierarchical ontologies a parent term can show a smaller `organism_gene_count` than its child; use `ontology_term_details(organism=...)` for subtree-scoped per-organism counts.

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
# returns dict with keys: mode, total_entries, total_matching, score_max, score_median, offset, by_ontology, by_level, by_interpro_type, by_family_type, skipped_ontologies, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
