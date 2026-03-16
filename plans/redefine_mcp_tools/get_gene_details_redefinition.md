# Plan: `get_gene_details` — curate response, fix duplicate homologs

Refactor `get_gene_details` to return curated gene properties instead of
dumping all 40 node properties. Fix duplicate homolog rows caused by
bidirectional edges. Drop raw ontology ID lists (GO, KEGG, EC) now that
dedicated ontology tools exist.

## Gene Property Distribution (35,226 genes across 13 strains)

Data from KG exploration on 2026-03-16. Four annotation sources feed
each gene node; all genes have NCBI + EggNOG, but Cyanorak and UniProt
coverage is partial.

### Data source coverage by organism group

| Source | Pro (7 Cyanorak strains) | Pro RSP50 | Alteromonas (3) | Synechococcus (2) |
|---|---|---|---|---|
| NCBI | yes | yes | yes | yes |
| EggNOG | yes | yes | yes | yes |
| Cyanorak | yes | no | no | yes |
| UniProt | partial | no | partial | partial (WH8102 only) |

RSP50 and CC9311 have **zero** UniProt-sourced properties.

### Property counts (KG-wide)

| Property | Count | % | Notes |
|---|---|---|---|
| `locus_tag`, `product`, `organism_strain`, `gene_summary`, `gene_category`, `annotation_quality`, `all_identifiers`, `alternate_functional_descriptions`, `preferred_id`, `id`, `product_source` | 35,226 | 100% | Universal |
| `alternative_locus_tags`, `gene_synonyms` | 33,904 | 96% | |
| `start`, `end`, `protein_id`, `locus_tag_ncbi` | 33,376 | 95% | Missing ~1,850 (no NCBI mapping) |
| `eggnog_ogs` | 32,454 | 92% | |
| `seed_ortholog`, `max_annot_lvl`, `seed_ortholog_evalue` | 32,295 | 92% | Pipeline metadata |
| `function_description`, `cog_category` | 29,236 | 83% | |
| `pfam_names` | 26,607 | 76% | |
| `bacteria_cog_og` | 26,298 | 75% | |
| `go_terms` | 23,013 | 65% | |
| `cluster_number` | 20,657 | 59% | Pro/Syn with Cyanorak only |
| `gene_name` | 18,868 | 54% | |
| `kegg_ko`, `kegg_brite` | 18,307 | 52% | |
| `pfam_ids` | 18,055 | 51% | |
| `tIGR_Role`, `tIGR_Role_description` | 18,037 | 51% | |
| `strand` | 16,899 | 48% | |
| `eggnog_og_descriptions` | 14,939 | 42% | |
| `pfam_descriptions` | 14,910 | 42% | |
| `cyanorak_Role`, `cyanorak_Role_description` | 14,616 | 41% | Pro/Syn only |
| `ec_numbers` | 13,082 | 37% | |
| `go_term_descriptions` | 12,258 | 35% | |
| `kegg_pathway` | 11,619 | 33% | |
| `alteromonadaceae_og` | 10,403 | 30% | Alteromonas only |
| `strand_cyanorak` | 10,316 | 29% | |
| `kegg_reaction` | 7,788 | 22% | |
| `kegg_module` | 7,469 | 21% | |
| `protein_family` | 6,113 | 17% | Single string, UniProt-sourced |
| `kegg_ko_descriptions` | 5,612 | 16% | |
| `transmembrane_regions` | 3,419 | 10% | |
| `catalytic_activities` | 2,740 | 8% | Long reaction strings |
| `transporter_classification` | 2,688 | 8% | |
| `bigg_reaction` | 2,009 | 6% | |
| `gene_name_synonyms` | 1,511 | 4% | |
| `signal_peptide` | 720 | 2% | |
| `cazy_ids` | ~370 | ~1% | |
| `subcellular_location` | 0 | 0% | Empty — not loaded by pipeline |
| `uniprot_accession` | 0 | 0% | Empty — not loaded into KG |

### List field sizes (for genes that have them)

| Field | Avg (Pro) | Avg (Alt) | Max | Notes |
|---|---|---|---|---|
| `go_terms` | 12.7 | 22.4 | 188 | Raw IDs — use `gene_ontology_terms` |
| `alternate_functional_descriptions` | 9.3 | 3.7 | 22 | Multi-sentence paragraphs from UniProt/EggNOG |
| `eggnog_ogs` | 8.0 | 5.1 | — | Pipeline internals |
| `all_identifiers` | 3.1 | 2.0 | ~5 | Short, compact |
| `pfam_names` | 1.5 | 1.7 | — | Short, compact |
| `kegg_ko` | 0.8 | 0.8 | — | Raw IDs |
| `ec_numbers` | 0.8 | 0.6 | — | Raw IDs |

### Cluster coverage (mutually exclusive)

| Field | Count | Organisms |
|---|---|---|
| `cluster_number` | 20,657 | Pro/Syn with Cyanorak (not RSP50) |
| `alteromonadaceae_og` | 10,403 | Alteromonas only |
| **coalesce (unified `cluster_id`)** | **31,060 (88%)** | |

### Homologs (PMM1428 example)

11 unique homologs (22 rows before dedup due to bidirectional edges):
- 3 cross-phylum (Alteromonas, via `eggnog_bacteria_cog_og`)
- 2 same-order Synechococcales
- 6 same-species Prochlorococcus marinus

---

## Issues Found in Review

### A. Duplicate homologs — every homolog appears twice

The KG stores bidirectional edges (A→B **and** B→A) for
`Gene_is_homolog_of_gene`. The undirected MATCH pattern matches both,
so every homolog pair returns 2 rows. PMM1428 has 11 unique homologs but
returns 22 rows. The `LIMIT 20` in `build_get_gene_details_homologs`
silently drops real results.

Same bug exists in `build_get_homologs` (used by the `get_homologs` tool).

### B. Property dump — `g {.*}` returns 40 properties, most useless

The query returns ALL gene node properties. ~60-70% are pipeline metadata,
redundant coordinate sets, or raw annotation lists that waste tokens:

| Category | Properties |
|---|---|
| Pipeline metadata | `seed_ortholog`, `seed_ortholog_evalue`, `max_annot_lvl`, `product_source`, `function_description_source`, `gene_name_source`, `preferred_id`, `id` |
| Redundant coordinates | `start_cyanorak`, `end_cyanorak`, `strand_cyanorak`, `locus_tag_cyanorak`, `locus_tag_ncbi`, `product_cyanorak` |
| Raw annotation dumps | `eggnog_ogs`, `eggnog_og_descriptions`, `cog_category`, `tIGR_Role`, `tIGR_Role_description` |
| Duplicate identifiers | `old_locus_tags`, `alternative_locus_tags`, `gene_synonyms` all overlap with `all_identifiers` |

### C. Raw ontology ID lists — useless without names

`go_terms` (avg 16, max 188 entries), `kegg_ko`, `kegg_pathway`,
`kegg_brite`, `kegg_reaction`, `kegg_module`, and `ec_numbers` are all
raw IDs without human-readable names. Now that `gene_ontology_terms` and
`search_ontology` exist, these should be removed.

### D. `_cluster` only works for Cyanorak organisms

The `OPTIONAL MATCH (g)-[:Gene_in_cyanorak_cluster]->(c:Cyanorak_cluster)`
only returns cluster info for Pro/Syn. Alteromonas genes get
`_cluster: null` even when they have `alteromonadaceae_og` as a gene
property. Cluster info is inconsistent across organisms.

### E. No expression data summary

The tool returns gene details + homologs but gives no indication whether
expression data exists. Users must make a separate `query_expression`
call to find out. Even a count would help Claude decide whether to follow up.

### F. `_protein` is null for ~65% of Alteromonas genes

UniProt protein records exist for only 28-35% of Alteromonas genes (vs
50-71% for Pro/Syn). This is a data coverage gap, not a bug. No code
change needed, but the docstring could note it.

## Out of Scope

- Changes to `resolve_gene`, `search_genes`, or ontology tools
- KG schema changes — see [kg_schema_improvements_for_gene_details.md](kg_schema_improvements_for_gene_details.md)
  for upstream improvements that would simplify the Gene node from ~40
  to ~17 properties (drop pipeline metadata, redundant identifiers,
  Cyanorak duplicates, ontology ID lists, fix bidirectional homolog
  edges, unify cluster_id). This plan works around them in the query layer.
- Changes to `query_expression` or `compare_conditions`

---

## Tool Signature

No signature change — same `gene_id` parameter. The return structure
changes: `_homologs` list replaced by `homolog_count` integer,
`alternate_functional_descriptions` dropped (redundant with
`gene_summary`), `protein_family` added.

```python
@mcp.tool()
def get_gene_details(ctx: Context, gene_id: str) -> str:
    """Get full details for a gene: functional annotations, protein,
    organism, ortholog cluster, and homolog summary.

    Args:
        gene_id: Gene locus_tag (e.g. "PMM0001", "sync_0001").

    Notes:
        - Protein data is UniProt-sourced; coverage varies by organism
          (~70% for Prochlorococcus, ~30% for Alteromonas).
        - For ontology annotations (GO, KEGG, EC), use gene_ontology_terms
          which returns terms with human-readable names.
        - For expression data, use query_expression with the gene locus_tag.
        - For full homolog list, use get_homologs with the gene locus_tag.
    """
```

**Return structure:**
```json
[{
  "locus_tag": "PMM1428",
  "gene_name": "...",
  "product": "...",
  "function_description": "...",
  "gene_summary": "...",
  "gene_category": "...",
  "annotation_quality": 3,
  "organism_strain": "Prochlorococcus MED4",
  "start": 1367679,
  "end": 1368140,
  "strand": "+",
  "protein_id": "WP_011133057.1",
  "all_identifiers": ["CK_Pro_MED4_01428", "TX50_RS07695", "WP_011133057.1"],
  "pfam_names": ["EVE"],
  "protein_family": null,
  "cluster_id": "CK_00001099",
  "homolog_count": 11,
  "expression_edge_count": 36,
  "_protein": {"gene_names": [...], "is_reviewed": "...", "annotation_score": 1.0,
               "sequence_length": 153, "refseq_ids": [...]},
  "_organism": {"preferred_name": "...", "strain_name": "MED4", "genus": "Prochlorococcus",
                "clade": "HLI", "ncbi_taxon_id": 59919}
}]
```

**Properties kept vs dropped:**

| Keep | Why |
|---|---|
| `locus_tag`, `gene_name`, `product` | Core identification |
| `function_description`, `gene_summary` | Functional annotation |
| `gene_category`, `annotation_quality` | Classification |
| `organism_strain` | Context |
| `start`, `end`, `strand` | Genomic position (one set only) |
| `protein_id` | Cross-reference to UniProt/RefSeq |
| `all_identifiers` | All alternate IDs in one place |
| `pfam_names` | Compact, human-readable domain annotations |
| `protein_family` (new) | Single string, 17% coverage, informative when present (e.g. "Beta sliding clamp family") |
| `cluster_id` (new, unified) | Ortholog cluster — `coalesce(cluster_number, alteromonadaceae_og)` |
| `homolog_count` (new, from separate query) | Integer — tells Claude whether to call `get_homologs` |
| `expression_edge_count` (new) | Tells Claude if expression data exists |

| Drop | Why |
|---|---|
| `alternate_functional_descriptions` | Redundant — `gene_summary` already combines best product + function_description; remaining entries are COG/KEGG/TIGR role descriptions and lower-priority source duplicates (avg 3.7 Alt, 9.3 Pro, max 22 entries with multi-sentence paragraphs) |
| `go_terms` | Raw IDs (avg 16, max 188) — use `gene_ontology_terms` |
| `kegg_ko`, `kegg_pathway`, `kegg_brite`, `kegg_reaction`, `kegg_module` | Raw IDs — use `gene_ontology_terms` with `ontology="kegg"` |
| `ec_numbers` | Raw IDs — use `gene_ontology_terms` with `ontology="ec"` |
| `pfam_ids`, `pfam_descriptions` | Redundant with `pfam_names` |
| `start_cyanorak`, `end_cyanorak`, `strand_cyanorak`, `locus_tag_cyanorak`, `product_cyanorak` | Duplicate coordinate/name sets from Cyanorak source |
| `locus_tag_ncbi` | Already in `all_identifiers` |
| `old_locus_tags`, `alternative_locus_tags`, `gene_synonyms` | Redundant with `all_identifiers` |
| `eggnog_ogs`, `eggnog_og_descriptions` | Pipeline internals |
| `cog_category`, `tIGR_Role`, `tIGR_Role_description` | Pipeline internals |
| `seed_ortholog`, `seed_ortholog_evalue`, `max_annot_lvl` | Pipeline internals |
| `product_source`, `function_description_source`, `gene_name_source` | Pipeline internals |
| `preferred_id`, `id` | Internal identifiers |
| `bacteria_cog_og` | Pipeline internal (COG cluster — `cluster_id` covers this) |
| `cluster_number`, `alteromonadaceae_og` | Replaced by unified `cluster_id` |

---

## Implementation Order

| Order | Change | Where | Status |
|-------|--------|-------|--------|
| 1 | Curate RETURN clause in `build_get_gene_details_main` | `queries_lib.py` | this plan |
| 2 | Fix homologs: count query in `build_get_gene_details_homologs`, dedup in `build_get_homologs` | `queries_lib.py` | this plan |
| 3 | Update tool wrapper — remove `_cluster` nesting, replace `_homologs` with `homolog_count`, add `expression_edge_count` | `tools.py` | this plan |
| 4 | Update tests | tests | this plan |
| 5 | Update docs | docs | this plan |

Steps 1 and 2 are independent. Step 3 depends on both.
Steps 4 and 5 can run in parallel after step 3.

## Agent Assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1+2 | **query-builder** | Curate RETURN clause in `build_get_gene_details_main` (add `protein_family`, drop `alternate_functional_descriptions`), change `build_get_gene_details_homologs` to count query, fix dedup in `build_get_homologs` | — |
| 3 | **tool-wrapper** | Update `get_gene_details` wrapper: drop `_cluster` nesting, replace `_homologs` list with `homolog_count` integer, add expression edge count from main query, update docstring. Update `get_homologs` wrapper if homolog response format changes. | 1+2 |
| 4a | **test-updater** | Update unit, integration, eval, and regression tests | 3 |
| 4b | **doc-updater** | Update `CLAUDE.md`, `docs/testplans/testplan.md` | 3 |
| 5 | **code-reviewer** | Review all changes against this plan, run unit tests | 4a, 4b |

---

## Query Builders

**File:** `queries_lib.py`

### `build_get_gene_details_main` — curated RETURN

Replace `g {.*}` with explicit property selection. Unify cluster_id.
Add expression edge count. Drop `Gene_in_cyanorak_cluster` OPTIONAL MATCH
(replaced by gene property).

```cypher
MATCH (g:Gene {locus_tag: $lt})
OPTIONAL MATCH (g)-[:Gene_encodes_protein]->(p:Protein)
OPTIONAL MATCH (g)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)
OPTIONAL MATCH (factor)-[expr:Condition_changes_expression_of|Coculture_changes_expression_of]->(g)
WITH g, p, o, count(expr) AS expression_edge_count
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.function_description AS function_description,
       g.gene_summary AS gene_summary,
       g.gene_category AS gene_category, g.annotation_quality AS annotation_quality,
       g.organism_strain AS organism_strain,
       g.start AS start, g.end AS end, g.strand AS strand,
       g.protein_id AS protein_id, g.all_identifiers AS all_identifiers,
       g.pfam_names AS pfam_names, g.protein_family AS protein_family,
       coalesce(g.cluster_number, g.alteromonadaceae_og) AS cluster_id,
       expression_edge_count,
       p {.gene_names, .is_reviewed, .annotation_score,
          .sequence_length, .refseq_ids} AS _protein,
       o {.preferred_name, .strain_name, .genus, .clade,
          .ncbi_taxon_id} AS _organism
```

**Key changes:**
- Explicit property list instead of `g {.*}` — ~15 useful properties vs 40
- `coalesce(g.cluster_number, g.alteromonadaceae_og) AS cluster_id` replaces
  the separate `Gene_in_cyanorak_cluster` OPTIONAL MATCH
- `count(expr) AS expression_edge_count` — single integer, tells Claude
  whether to follow up with `query_expression`
- `protein_family` added — single string, 17% coverage (UniProt-sourced)
- `alternate_functional_descriptions` dropped — `gene_summary` already
  captures the best annotations; the full list averaged 9+ entries for
  Pro/Syn with multi-sentence paragraphs
- All ontology ID lists dropped (`go_terms`, `kegg_*`, `ec_numbers`)
- All pipeline metadata dropped
- No more `_cluster` nested object — just a flat `cluster_id` string

**Return shape change:** The response was `g {.*}` (a map with _protein,
_organism, _cluster nested inside). The new response returns flat columns.
The tool wrapper must assemble them into the response dict, adding
`homolog_count` from the separate count query (see Tool Wrapper Logic
below).

### `build_get_gene_details_homologs` — count instead of list

Replace the full homolog list with a deduplicated count. The
`get_homologs` tool provides full details when needed.

```cypher
MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)
WITH DISTINCT other.locus_tag AS lt
RETURN count(lt) AS homolog_count
```

**Note:** `WITH DISTINCT` deduplicates the A→B / B→A pairs from
bidirectional edges before counting. PMM1428 returns 11 (not 22).
The `LIMIT 20` is removed entirely — we only return one integer.

### `build_get_homologs` — same dedup fix

Apply the same `DISTINCT` fix. This query already has no LIMIT.

```cypher
MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)
RETURN DISTINCT other.locus_tag AS locus_tag, other.product AS product,
       other.organism_strain AS organism_strain,
       h.distance AS distance, h.cluster_id AS cluster_id,
       h.source AS source
ORDER BY h.distance, other.locus_tag
```

---

## Tool Wrapper Logic

**File:** `tools.py`

The main query no longer returns `g {.*}` as a nested map. The wrapper
must assemble the flat columns into the response dict:

```python
def get_gene_details(ctx: Context, gene_id: str) -> str:
    conn = _conn(ctx)

    # Main gene + protein + organism + expression count
    cypher_main, params_main = build_get_gene_details_main(gene_id=gene_id)
    main = conn.execute_query(cypher_main, **params_main)
    if not main:
        return f"Gene '{gene_id}' not found."

    row = main[0]
    # Check for no gene match (all columns will be None)
    if row.get("locus_tag") is None:
        return f"Gene '{gene_id}' not found."

    # Homolog count (deduplicated)
    cypher_hom, params_hom = build_get_gene_details_homologs(gene_id=gene_id)
    hom_result = conn.execute_query(cypher_hom, **params_hom)

    # Assemble result — _protein and _organism are already maps from Cypher
    result = {k: v for k, v in row.items() if not k.startswith("_")}
    result["homolog_count"] = hom_result[0]["homolog_count"] if hom_result else 0
    result["_protein"] = row.get("_protein")
    result["_organism"] = row.get("_organism")

    response = _fmt([result])
    # debug handling same as current
```

**Key differences from current:**
- The current wrapper does `result = main[0]["gene"]` because the old query
  returns `g {.*} AS gene`. The new query returns flat columns.
- `_homologs` list replaced by `homolog_count` integer from the count query.
- The "not found" check changes from `main[0]["gene"] is None` to
  `row.get("locus_tag") is None` (or `not main`).

---

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**

`TestBuildGetGeneDetails`:
- [ ] Main query returns explicit columns, not `g {.*}`
- [ ] `go_terms` NOT in main query RETURN clause
- [ ] `kegg_ko`, `kegg_pathway`, `kegg_brite`, `kegg_reaction`, `kegg_module` NOT in RETURN
- [ ] `ec_numbers` NOT in RETURN
- [ ] `seed_ortholog`, `eggnog_ogs`, `cog_category` NOT in RETURN
- [ ] `cluster_id` uses `coalesce(g.cluster_number, g.alteromonadaceae_og)`
- [ ] `expression_edge_count` in RETURN (via count of expression edges)
- [ ] `_protein` map includes expected fields
- [ ] `_organism` map includes expected fields
- [ ] No `Gene_in_cyanorak_cluster` OPTIONAL MATCH
- [ ] Homologs query uses `WITH DISTINCT` and returns `count` (not a list)
- [ ] Homologs query has no `LIMIT`
- [ ] `protein_family` in RETURN clause
- [ ] `alternate_functional_descriptions` NOT in RETURN clause
- [ ] Expected columns present: `locus_tag`, `gene_name`, `product`, `function_description`, `gene_summary`, `gene_category`, `annotation_quality`, `organism_strain`, `start`, `end`, `strand`, `protein_id`, `all_identifiers`, `pfam_names`, `protein_family`, `cluster_id`, `expression_edge_count`

`TestBuildGetHomologs`:
- [ ] Homologs query has `DISTINCT` in RETURN

**`tests/unit/test_tool_wrappers.py`:**

`TestGetGeneDetailsWrapper`:
- [ ] Not found returns message (empty results)
- [ ] Not found returns message (locus_tag is None)
- [ ] Response includes `homolog_count`, `_protein`, `_organism`
- [ ] Response does NOT include `_homologs` (list replaced by count)
- [ ] Response includes `cluster_id` (not `_cluster`)
- [ ] Response includes `expression_edge_count`
- [ ] Response includes `protein_family`
- [ ] Response does NOT include `go_terms`, `kegg_ko`, `ec_numbers`
- [ ] Response does NOT include `alternate_functional_descriptions`

`TestGetHomologsWrapper`:
- [ ] Existing tests still pass with DISTINCT (no behavior change)

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

- [ ] Pro gene (PMM1428): has `cluster_id` (Cyanorak), `_protein` present, expression_edge_count > 0
- [ ] Alt gene (MIT1002_03493): has `cluster_id` (eggNOG OG), `_protein` is null, expression_edge_count > 0
- [ ] Response does NOT contain `go_terms`, `kegg_ko`, `ec_numbers`, `seed_ortholog`, `eggnog_ogs`, `alternate_functional_descriptions`
- [ ] `homolog_count` is integer: PMM1428 should be 11 (not 20+)
- [ ] Gene not found returns message string
- [ ] `pfam_names` present and is a list
- [ ] `protein_family` present (may be null for genes without UniProt data)

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: gene_details_has_organism
  tool: get_gene_details
  desc: Gene details includes organism info
  params:
    gene_id: PMM1428
  expect:
    min_rows: 1
    contains:
      _organism.strain_name: MED4

- id: gene_details_alteromonas
  tool: get_gene_details
  desc: Alteromonas gene has cluster_id from eggNOG OG
  params:
    gene_id: MIT1002_03493
  expect:
    min_rows: 1

- id: gene_details_synechococcus
  tool: get_gene_details
  desc: Synechococcus gene details
  params:
    gene_id: SYNW0529
  expect:
    min_rows: 1
```

### Regression snapshots (`tests/regression/`)

Existing `gene_details_*` baselines must be regenerated — response shape
changes (curated properties, no `_cluster`, no `_homologs` list, added
`cluster_id`, `homolog_count`, `protein_family`, and
`expression_edge_count`).

```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Update `get_gene_details` description in MCP Tools table: "Full gene profile: functional annotations, protein, organism, cluster, homologs, expression count" |
| `docs/testplans/testplan.md` | Add test plan section for get_gene_details changes |
