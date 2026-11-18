# Backlog 2d.4: `genes_by_ontology` across organisms

Status: **frozen** 2026-11-18 (user-approved).

Mode A (one tool, with shared-builder changes). Origin: spock hli_light_stress analysis
2026-11-16 ("which strains carry InterPro X" over ~100 strains needed a loop or Cypher).
Design settled with the user 2026-11-18. All Cypher below was verified on the release KG
(alpha.9, 118 organisms with genes, 330,531 genes) on 2026-11-18.

## Why

`organism` is required and single today. A presence question across strains ("which
Prochlorococcus carry HliA-D, and how many copies") means one call per organism. The
backlog item asked for either `organism: str | list[str] | None` or a separate presence
mode. Decision: the list / None form on the same tool, with `by_organism` in the envelope,
so `summary=True` answers presence and absence.

Investigating the cross-organism cost exposed two defects in the existing builders that
this item fixes, because the cross-organism path cannot work without the fixes:

1. **Quadratic detail memory.** The match stage ends `collect(DISTINCT g) AS term_genes`
   and the detail query then `UNWIND term_genes AS g`. Every unwound row keeps the whole
   list in its slot, and the planner sorts these rows before `LIMIT`, so memory grows with
   N². PROFILE: 3,012 rows used 257 MB in `PartialSort`. Any detail call whose terms
   reach about 6,000 genes fails with `MemoryPoolOutOfMemoryError` (717 MB transaction
   limit), even with `limit=100`. Projecting the list away (`WITH t, g`) is optimised out
   by the planner, and a keys-only first query fails the same way. Single-organism calls
   hit this only when one genome puts ~6k genes under one term, which is rare, so it has
   not surfaced.
2. **Slow trust rollups on GO.** The aggregate trust-rollup query (Query C) re-walks the
   hierarchy from each (gene, term) row to find the best edge, about 2 ms per row. GO BP
   level 3 summary costs 7.9 s for MED4 and 16.3 s for EZ55 today; across all organisms it
   would be 1,220 s.

## API contract

### `organism: str | list[str] | None`

| Value | Meaning | Resolution |
|---|---|---|
| `str` | One organism, as today. | `_validate_organism_inputs`, unchanged: no match or several matches raise `ValueError`. |
| `list[str]` | These organisms. | Each entry word-matched with `build_resolve_organism_for_organism`; an entry may expand to several organisms (`"Prochlorococcus"` → 45). Union, de-duplicated. Entries that match nothing go to `not_found_organisms`; if every entry is unknown, the envelope is empty (no raise). An empty list raises `ValueError("organism list must not be empty.")`. |
| `None` | Every organism with genes (118 today). | No resolution query. |

`organism` stays the second positional parameter and gains the default `None`, so
existing positional calls keep working. The single-string path is byte-identical in
Cypher to today except where the fixes below change it.

Note: word matching carries backlog 2.8's leak (`"AltDE"` → AltDE and AltDE1). Documented,
not fixed here.

### Size bounds: off by default across organisms

`min_gene_set_size` / `max_gene_set_size` are counted **per (term, organism)**: a term's
gene set inside one genome. With a single organism this is today's meaning.

The defaults are already distinguishable from explicit values: they are the
`_DefaultGeneSetSize` markers `GENE_SET_SIZE_MIN_DEFAULT` (5) /
`GENE_SET_SIZE_MAX_DEFAULT` (500), detected by `_is_default_size` (the MCP wrapper uses
the same markers as its defaults). The API resolves a bound that is still a marker:

- one organism (`str`): the marker's value, 5 / 500, as today;
- list or `None`: no bound (`min` → 1, `max` → `None`).

Reason: HliA-D (IPR063966) has 3–4 genes in 50 of its 102 strains, and IPR054650 has exactly
1 gene in each of its 100 strains, so 5 / 500 per genome would silently drop half or all of
a presence answer. Explicit values (including an explicit 5 or 500) always apply, per
(term, organism). `max_gene_set_size=None` keeps meaning "unbounded". No signature or
default changes, so no breaking change for Python or MCP callers.

The size warning (`_size_warning_due`) is unchanged: it fires when terms were dropped and
a bound is still a marker. Across organisms the markers resolve to no bounds, so nothing
is dropped and it cannot fire unless a bound is explicit.

### Rows

- New compact column `organism_name`, on every row, single-organism calls included,
  placed right after `locus_tag`.
- Order: `organism_name, term_id, locus_tag`. Each row is unique (locus tags are unique
  KG-wide), so the order is total and pages never overlap. With one organism this is
  today's `term_id, locus_tag` order.

### Envelope

| Key | Change |
|---|---|
| `organism_name` | `str` when one organism is in scope, else `None`. Type becomes `str \| None`. |
| `by_organism` (new) | `[{organism_name, gene_count, term_count, row_count}]`, organisms with ≥1 row, sorted `gene_count` desc then name. `sum(row_count) == total_matching`. |
| `organisms_without_genes` (new) | Resolved organisms in scope with 0 rows, sorted by name. For `None` this is every organism with genes that has no row (can be ~117 names on a narrow term). For a single string: `[]` or `[that organism]`. |
| `not_found_organisms` (new) | List entries that matched no organism. `[]` for `str` / `None`. |
| `top_terms` | Each entry gains `organism_count`. `count` = rows summed across organisms. |
| `total_terms`, `by_level.n_terms` | Distinct terms (across organisms). |
| `genes_per_term_min/median/max` | Over (term, organism) gene sets, i.e. per-genome set sizes. Same as today for one organism. |
| `size_filtered_terms` | Counts dropped (term, organism) gene sets. Same as today for one organism. |

Everything else (`trust_axes`, `by_evidence`, `by_tier`, `by_sources`, `by_call_class`,
`by_tcdb_call`, `evidence_score_stats`, `filters_applied`, `warnings`, `not_found`,
`wrong_ontology`, `wrong_level`, `filtered_out`, `resolved_aliases`) keeps its meaning over
the whole cross-organism match.

### Unchanged

All three modes (term_ids / level / both), every ontology, every trust filter and facet,
`informative_only`, `include_weak_tcdb_hits`, `verbose`, `summary`, MCP `limit=50`
default. No cap on level-only mode across organisms: bucket paging (below) bounds every
page.

## Query architecture

Five builder changes (C1–C5) plus API-side paging. Builders keep their names.

### C1. Organism scope in the match stage

`_genes_by_ontology_match_stage(organisms=...)` where the API passes a `str`, a resolved
`list[str]`, or `None`:

- `str`: `(g:Gene {organism_name: $org})`, unchanged.
- `list`: `(g:Gene)` and `g.organism_name IN $orgs` `_and_join`ed into the gene→leaf
  WHERE that already carries the trust and gate predicates (every branch has that WHERE
  slot).
- `None`: `(g:Gene)`, no predicate.

### C2. Size filter per (term, organism)

`WITH t, collect(DISTINCT g) AS term_genes` becomes
`WITH t, g.organism_name AS org, collect(DISTINCT g) AS term_genes`; the TCDB weak-sizing
variant carries `org` through its two extra WITHs. Downstream tails carry `org`.

### C3. Query A: per-term → per bucket

`build_genes_by_ontology_per_term` returns one row per **bucket** (organism, term):
`organism_name, term_id, term_name, level, tree, tree_code, best_effort, n_genes,
cat_freqs, is_informative`, `ORDER BY organism_name, term_id`. The API derives the
per-term envelope fields by summing buckets per term, and plans pages from the buckets.

### C4. Query B: per-gene carries organism

`build_genes_by_ontology_per_gene` adds `g.organism_name AS organism_name`. Feeds
`by_organism.gene_count`.

### C5. Query C: trust rollups from the head's own edges

Replace the re-walk rebind (`[(g)-[r2]->(l2)-[:is_a*0..]->(t) | {...}]`) in
`build_genes_by_ontology_trust_rollups` with the edges the head already bound:

```cypher
<head: gene -[r]-> leaf, walk leaf -> t, trust + gate + organism predicates on r>
WITH DISTINCT t, g, r, leaf
WHERE <bucket filter, only when size bounds are active:
       $bucket_set[g.organism_name + '|' + t.id]>
WITH t, g, collect({evidence: r.evidence, sources: r.sources, ...,
                    attachment_level: leaf.level, attachment_id: leaf.id,
                    sources_key: ...}) AS edges
WITH t, g, head(apoc.coll.sortMulti(edges, <same rank keys>)) AS r
<unchanged aggregation tail>
```

The edge map and rank keys are exactly today's, with `r2` → `r`, `l2` → `leaf`. No
`collect` of genes, so no list carry. `$bucket_set` is a map `{"<org>|<term_id>": true}`
built from Query A's buckets (O(1) lookup; up to ~17k keys for GO level 3 across all
organisms). With bounds off the filter is omitted. Flat ontologies (`cog_category`,
`ncbifam`, `subcellular_localization`, `signal_peptide_type`) keep their direct
`OPTIONAL MATCH` rebind and change only by C1/C2.

### C6. Query D: detail driven by the page's buckets

`build_genes_by_ontology_detail` takes `buckets: list[{organism_name, term_id}]` plus an
inner `offset` / `limit`, and no size bounds (buckets are already sized):

```cypher
<head in the caller's mode, term_ids := the page's distinct term_ids,
 organism scope := the page's distinct organisms>
WITH DISTINCT t, g
WHERE g.organism_name IN $orgs AND g.organism_name + '|' + t.id IN $bucket_keys
<unchanged best-edge rebind + RETURN, organism_name added>
ORDER BY organism_name, term_id, locus_tag
SKIP $offset LIMIT $limit
```

Level-only mode becomes Mode 3 for the page (level + the page's terms), which the
existing builder already supports. `$bucket_keys` holds only the page's buckets (≤ limit
entries) and drops the cross-product pairs that the org × term narrowing would admit.

### API paging (Query D planner)

1. Query A returns buckets sorted `(organism_name, term_id)` with `n_genes`.
2. For `offset` / `limit`, walk cumulative `n_genes` and take the buckets overlapping
   `[offset, offset + limit)`; inner offset = `offset` − start of the first such bucket.
3. One Query D call with those buckets.
4. `limit=None` (full fetch, Python callers and the enrichment tools): the same planner
   in chunks of buckets summing to ≤ 20,000 rows each (a larger single bucket goes alone;
   the largest single-genome bucket seen is ~3.8k), results concatenated.

`total_matching` = sum of bucket `n_genes`, known before any detail query, as today.

## Verified Cypher (release KG alpha.9, 2026-11-18)

Prototype = string transforms of today's builder output implementing C1–C6; scripts kept
out of the repo. Times are wall-clock from Python.

### Single organism: identical to today

MED4 and Alteromonas macleodii EZ55, default bounds 5 / 500, 14 cases: go_bp level 3,
go_bp term, kegg level 1, kegg level 2 + term_ids, cyanorak_role level 1, pfam level 0
(clan), ec level 1, cog_category (flat), tcdb level 1, tcdb + `include_weak_tcdb_hits`,
interpro FAMILY, brite tree=transporters, go_bp + `evidence` filter, kegg level 2 +
`informative_only`. For all 28: detail rows concatenated over pages of 100 (C6 + planner)
== today's unpaged detail, same order; Query A buckets == today's per-term rows (plus
`organism_name`); Query B == today's per-gene rows (plus `organism_name`).

C5 rollups == today's rollups for every ontology using the best-edge rebind (go_bp, go_mf,
go_cc, ec, kegg, cyanorak_role, tigr_role, pfam, brite, tcdb incl. weak, cazy, interpro,
merops), level 1, with and without an `evidence` filter, MED4 and EZ55, bounds 5 / 500,
plus go_bp level 3 and a go_bp term. Faster where it mattered:

| Rollups | Today | C5 |
|---|---|---|
| go_bp level 3, MED4 | 7.89 s | 0.15 s |
| go_bp level 3, EZ55 | 16.32 s | 0.15 s |
| go_bp level 1 + evidence, EZ55 | 2.91 s | 0.03 s |

### Across organisms

`LIST4` = MED4, MIT9313, WH8102, EZ55. `ALL` = `None`.

| Scope | Bounds | Case | Buckets | Rows | Query A | Query B | Query C (C5) | Page @0 / @50k / @500k |
|---|---|---|---|---|---|---|---|---|
| ALL | off | go_bp level 3 | 16,751 | 574,643 | 6.2 s | 9.0 s | 13.8 s | 0.22 / 0.91 / 1.35 s |
| ALL | 5/500 | go_bp level 3 | 9,212 | 379,337 | 5.1 s | 8.2 s | 9.7 s | 0.10 / 0.78 s |
| ALL | off | kegg level 1 | 2,722 | 155,259 | 1.1 s | 3.7 s | 3.3 s | 0.06 / 0.06 s |
| ALL | off | kegg "Metabolism" term | 118 | 74,284 | 0.5 s | 2.4 s | 1.4 s | 0.29 / 0.30 s |
| ALL | off | 2 hli InterPro terms | 202 | 600 | 0.1 s | 0.1 s | 0.2 s | 0.10 s |
| LIST4 | off | go_bp level 3 | 625 | 23,002 | 3.7 s | 3.8 s | 3.4 s | 0.06 s |
| LIST4 | 5/500 | kegg level 1 | 86 | 5,553 | 0.4 s | 0.5 s | 0.5 s | 0.05 s |

Every page: rows sorted by `(organism_name, term_id, locus_tag)`, page k's last key < page
k+1's first key. C5 `total_rows` == Query A row sum in every case; on LIST4 C5 output ==
the old rebind's output.

Oracle (LIST4, bounds 5 / 500, kegg level 1 and the hli terms): each organism's slice of
the cross-organism rows == that organism's single-organism call (1,086 / 1,160 / 1,270 /
2,037 rows for kegg), global order total, no duplicates.

Worst case (summary, ALL, go_bp level 3, bounds off): ~29 s over three queries, each under
the 30 s driver timeout. With explicit bounds the size-diagnostic reruns (A' / B') add
~15 s. Acceptable for an organism-wide GO rollup; narrower scopes are seconds.

Before the fixes, the same detail calls failed with `MemoryPoolOutOfMemoryError` at
≥ ~6k genes per term (`kegg.pathway:ko00195` 6,058 genes, `go:0009451` 6,161,
`interpro:IPR003593` 7,514), including at offset 0 with limit 100.

### Organism resolution

`build_resolve_organism_for_organism`: `"MED4"` → 1, `"Prochlorococcus"` → 45,
`"Alteromonas"` → 11, `"AltDE"` → 2 (2.8 leak), `"nope"` → 0.

## Degenerate inputs

| Input | After |
|---|---|
| `organism=[]` | `ValueError("organism list must not be empty.")` |
| `organism=["nope"]` | Empty envelope, `not_found_organisms=["nope"]`, no raise |
| `organism=["MED4", "nope"]` | MED4 answers; `not_found_organisms=["nope"]` |
| `organism=["MED4", "Prochlorococcus MED4"]` | De-duplicated to one organism |
| `organism=None`, term with no genes anywhere | Empty envelope; `organisms_without_genes` = all 118 |
| `organism="nope"` (str) | `ValueError`, as today |
| `organism="Alteromonas"` (str) | `ValueError` (matches several), as today; the message suggests passing a list |
| `offset` ≥ `total_matching` | `results=[]`, `truncated=False`, no detail query |

## Out of scope

- `pathway_enrichment` / `cluster_enrichment` / `ontology_landscape` stay single-organism
  (per-genome background). The two enrichment tools reach C1–C6 through
  `genes_by_ontology` and the shared builders, with identical results.
- Fixing organism word-match leaks (backlog 2.8).
- Pushing Query B's per-gene rollup into Cypher (160k rows to Python for ALL go_bp
  level 3, 9 s). Revisit if it bites.

## Docs

- `inputs/tools/genes_by_ontology.yaml`: cross-organism example (hli presence with
  `summary=True` → `by_organism` / `organisms_without_genes`); mistakes: size bounds are
  per genome and off by default across organisms; a list entry can expand to many
  strains; a single string must name one organism.
- Pydantic `organism` description: "One organism, a list (each entry word-matched and may
  expand to several strains), or omit for all organisms."
- Tool docstring: drop "in ONE organism"; CLAUDE.md tool row likewise.
- CHANGELOG `### Added`: cross-organism `genes_by_ontology`. `### Changed`: compact
  `organism_name` column on every row; size bounds off by default when more than one
  organism is in scope. `### Fixed`: detail out-of-memory on large terms; GO summary /
  paged latency (~50×).

## Tests

- Unit (builders): C1 for `str` / `list` / `None` (exact predicate, `$org` vs `$orgs`
  present, no `{organism_name: $org}` when not single); C2 grouping key in every branch
  incl. TCDB weak sizing; C3 / C4 RETURN keys; C5 contains no `[(g)-[r2` pattern
  comprehension and contains `$bucket_set` only when bounds are active; C6 has no
  `collect(DISTINCT g)`, has `$bucket_keys`, orders by `organism_name, term_id,
  locus_tag`.
- Unit (API): bucket page planner (offset inside a bucket, spanning many tiny buckets,
  exact bucket boundary, offset past the end, `limit=None` chunking); size-marker
  resolution per scope (marker vs explicit 5 / 500, `max=None`); organism resolution (list expansion, de-dup, not_found, empty
  list raise); envelope keys and `sum(by_organism.row_count) == total_matching`.
- Unit (wrappers): `organism` accepts str / list / None; new envelope fields; row
  `organism_name`.
- Edge-case scenarios: the degenerate-input table above.
- Regression: every existing `genes_by_ontology`, `pathway_enrichment` and
  `cluster_enrichment` golden unchanged except the added `organism_name` column and the
  new envelope keys (classified diff). New cross-organism cases: hli presence (ALL,
  summary), LIST4 kegg level 1 page 2, ALL go_bp level 3 summary.
- Integration (`-m kg`): the single-organism equivalence matrix above as a live test
  (today's semantics frozen as expectations: per-organism slice == single call), and one
  ALL go_bp level 3 summary under 45 s.
