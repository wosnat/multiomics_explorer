# GO transport follow-ups (Mode B: gene_overview, list_organisms, genes_by_metabolite, metabolites_by_gene + docs)

**Status:** FROZEN 2026-10-23 (user-approved) · **KG:** dev build
`built_at 2026-10-19T17:03:46.14Z` (`0.0.0-dev`) · **Backlog:** 2c.14, 2c.15, 2c.16, 2c.17 ·
**Parent:** `docs/tool-specs/go-transport-surface.md` (GO arm, row keys, sort keys — unchanged
here). Additive; no KG ask (every value derives from edges / properties already in the KG); no
`mcp_min_version` bump.

## 1. Purpose

Four small additions that make the GO transport route readable without walking rows:
a per-gene and per-organism GO metabolite count (mirrors of `transported_metabolite_count`),
GO-arm filters by namespace and gene→GO evidence, and a route-agreement rollup — the gene ×
metabolite pairs where catalysis / TCDB / GO agree are the confident core (design §1 of the parent).

## 2. Out of scope

TCDB diamond best hit; `Gene_has_tcdb_family.go_support` (KG's TCDB↔GO corroboration flag —
left for the TCDB redesign); per-row route lists on detail rows (paging makes them need the full
pair set); splitting `transport` by `substrate_depth` in the agreement rollup (decided: one route —
callers add `substrate_depth=['most_specific']` for the strict core); counting `ChemicalRole`
targets in the new counts; inherited (is_a ancestor) GO paths in the new counts; backlog 3.18
(`limit=None` TypeError on gbm / mbg — still open).

## 3. KG facts (verified live, built_at 2026-10-19T17:03:46Z)

| Fact | Live value |
|---|---|
| `Gene.transported_metabolite_count` definition | distinct `Metabolite` targets (no roles) at the deepest TCDB attachment — equal to a live walk on 300/300 sampled genes |
| `OrganismTaxon.transported_metabolite_count` | union of the same over the organism's genes (equal on every organism checked) |
| No KG precompute for GO counts | Gene / OrganismTaxon carry no GO-route property; none needed (below) |
| `Metabolite.go_transport_organism_names` | count per organism equals the live walk Gene→GO→Metabolite (direct, metabolite targets) on all 43 organisms with genes; 47-organism scan 0.1 s |
| Per-gene GO count, live | 1,000 KT2440 genes in 0.04 s; max 14 per gene |
| Gene→GO `evidence` vocab | `ControlledVocabulary` `Gene_enables_molecular_function.evidence` = `Gene_involved_in_biological_process.evidence` = `[curated, family_inferred, domain_inferred]` |
| Namespace | fixed by the gene→GO edge type: `Gene_enables_molecular_function` ↔ `molecular_function`, `Gene_involved_in_biological_process` ↔ `biological_process` (is_a never crosses namespace, so `type(r)` and `type(t)` agree on every row incl. inherited) |
| MED4 urea GO rows | 11 = BP curated 7 + MF curated 4 |

## 4. Changes per tool

### 4.1 `gene_overview` (2c.14)

- **Row, compact:** `go_transport_metabolite_count: int` (0 default) — distinct `Metabolite`
  targets reached through the gene's own GO terms (direct only; `ChemicalRole` targets excluded),
  placed after `transported_metabolite_count`. Field description: mirror of
  `transported_metabolite_count` for the GO route; a term definition count, not a gene fact; roles
  and is_a-inherited targets not counted; drill in with `metabolites_by_gene`.
- No envelope change (`evidence_sources` already tags the route).

```cypher
-- verified: PMM0970 urtA → 1, PMM0974 urtE → 3, PMM0392 → 0, PMM0001 → 0
COUNT { MATCH (g)-[:Gene_enables_molecular_function|Gene_involved_in_biological_process]->()
        -[:Molecular_function_transports_metabolite|Biological_process_transports_metabolite]->(m:Metabolite)
        RETURN DISTINCT m } AS go_transport_metabolite_count
```

Use a module constant next to `GO_TRANSPORT_EXISTS` (metabolite-only target edges).

### 4.2 `list_organisms` (2c.16)

- **Row, compact:** `go_transport_metabolite_count: int` (0 default), after
  `transported_metabolite_count`. Field description: metabolites reached by the organism's genes
  through GO transport terms (direct, metabolite targets) — same set as `list_metabolites`
  `go_transport_organism_names`.
- `top_metabolic_capability[]` entries gain `go_transport_metabolite_count` as a ride-along column
  (ranking unchanged: catalysis). Source in summary mode = `build_list_organisms_capability`
  (add the column there too).

```cypher
-- verified: MED4 45, KT2440 144, AltDE 94, MIT1314 25; 47 organisms in 0.1 s
COUNT { MATCH (m:Metabolite)
        WHERE o.preferred_name IN coalesce(m.go_transport_organism_names, []) }
  AS go_transport_metabolite_count
```

### 4.3 `genes_by_metabolite` + `metabolites_by_gene` — GO-arm filters (2c.15)

- **Params** (both tools, api + MCP), placed after `go_include_ancestors`:
  - `go_namespace: list[str] | None = None` — values `molecular_function` / `biological_process`
    (MCP `list[Literal[...]]`). Unknown values raise `ValueError` naming the allowed pair.
  - `go_evidence: list[str] | None = None` — validated against the union of the two GO
    `ControlledVocabulary` nodes (pivot fallback + warning per layer rules, never a hard-coded
    list). Unknown values raise `ValueError` with the allowed list (same strictness as
    `substrate_depth`).
- **Scope:** GO arm only (like `substrate_depth` for transport). Metabolism / transport rows untouched.
  Applied in both branches of `_go_transport_call` (direct + inherited). Threaded to every builder
  that emits the GO arm: GO detail builders, both summaries, `build_metabolites_by_gene_no_formula_count`,
  and the gbm stereo-relative counting call (relative counts must equal a re-call). The mbg stereo
  hint keeps its existing design (a default gbm call that ignores `evidence_sources` /
  `go_include_ancestors`, pinned by `test_mbg_stereo_ignores_evidence_sources_and_ancestors`), so
  it ignores the GO filters too.
- **Ancestor dedup stays unfiltered:** the inherited branch's `NOT EXISTS` (no direct GO path for
  the pair) is not narrowed by the filters, so a filtered result is always a subset of the
  unfiltered one. Document in the param description.
- **Arm off:** if `go_namespace` or `go_evidence` is set and `go_transport` is not in the active
  arms, ignore it and append a warning:
  `"go_namespace / go_evidence apply to the go_transport arm only, which evidence_sources excluded — filter ignored."`
  (name only the param(s) actually set).
- **Where helper:** `_genes_by_metabolite_go_transport_where` / `_metabolites_by_gene_go_transport_where`
  gain `go_namespace` / `go_evidence`; conditions bind `r` (the gene→GO edge, bound in both branches):

```cypher
-- verified: urea MED4 MF+curated 4 of 11; siderophore KT2440 direct 17 of 51, inherited 21 of 59;
-- every returned row has the filtered namespace + evidence; direct and inherited both correct
type(r) IN $go_gene_edge_types          -- mapped api/builder-side from go_namespace
r.evidence IN $go_evidence
```

### 4.4 `genes_by_metabolite` + `metabolites_by_gene` — route agreement (2c.17)

A **pair** = (gene, `metabolite_id`) after all filters; its **evidence sources** = the sorted set of
arms with ≥1 row for that pair (`metabolism` / `transport` / `go_transport`; transport is one
route regardless of `substrate_depth`; role ids are their own target).

- **Envelope (both tools):** `by_evidence_source_combination: list[{evidence_sources: list[str], pair_count: int}]`,
  sorted `pair_count` desc then `evidence_sources`. Always present (`[]` on an empty result).
- **Per-entity:**
  - gbm `by_metabolite[]` and mbg `top_metabolites[]`: `multi_source_gene_count` — genes reaching
    that metabolite through ≥2 sources.
  - gbm `top_genes[]` and mbg `by_gene[]`: `multi_source_metabolite_count` — metabolites that gene
    reaches through ≥2 sources.
- Field descriptions say: agreement = independent routes naming the same pair; routes are
  correlated (InterPro2GO and eggNOG share homology), so agreement raises confidence, it does not
  prove; a single-source pair is not wrong.

**Summary Cypher change (both summary builders):** replace the line after the arm `CALL {…}`

```cypher
WITH g, r, tf, m, es, sdepth, tscore, go, gdepth
```

with a pair-grouping pass, then carry `pair_sources` into the `rows` collect map:

```cypher
WITH g, m, collect({r: r, tf: tf, es: es, sdepth: sdepth, tscore: tscore, go: go, gdepth: gdepth}) AS arm_rows
WITH g, m, arm_rows, apoc.coll.sort(apoc.coll.toSet([x IN arm_rows | x.es])) AS pair_sources
UNWIND arm_rows AS x
WITH g, x.r AS r, x.tf AS tf, m, x.es AS es, x.sdepth AS sdepth, x.tscore AS tscore,
     x.go AS go, x.gdepth AS gdepth, pair_sources
...
collect({ ..., go_term_depth: gdepth, pair_sources: pair_sources }) AS rows
...
[cc IN apoc.coll.toSet([row IN rows | row.pair_sources]) |
   {evidence_sources: cc,
    pair_count: size(apoc.coll.toSet([row IN rows WHERE row.pair_sources = cc
                                       | row.locus_tag + '|' + row.metabolite_id]))}]
  AS by_evidence_source_combination
-- per metabolite: size(apoc.coll.toSet([row IN rows WHERE row.metabolite_id = mid
--                    AND size(row.pair_sources) > 1 | row.locus_tag])) AS multi_source_gene_count
-- per gene:       size(apoc.coll.toSet([row IN rows WHERE row.locus_tag = lt
--                    AND size(row.pair_sources) > 1 | row.metabolite_id])) AS multi_source_metabolite_count
```

Verified against live KG (built_at 2026-10-19T17:03:46Z): `total_matching` unchanged and the
combination counts equal the pairs regrouped from the full detail rows in every case:

| Call | Combinations (pair_count) |
|---|---|
| gbm urea, MED4 | transport 20 · go_transport+transport 5 (urtA–E) · metabolism 4; urea `multi_source_gene_count` 5 |
| gbm siderophore role, KT2440 | transport 144 · go_transport 26 · go_transport+transport 1 |
| gbm Gln/Glu/Asp, MED4 | metabolism 67 · transport 28 · go_transport+transport 1 (on Glu) |
| mbg urtA/urtB/urtE, MED4 | transport 8 · go_transport+transport 3 · go_transport 3 |
| mbg 60 MED4 chemistry genes | transport 1,873 · metabolism 327 · go_transport+transport 5 · metabolism+transport 2 · go_transport 1 |

Timing: mbg 60-gene summary 1.42–1.52 s before vs 1.48 s after (noise).

Detail builders, sort keys and row keys: unchanged.

## 5. Docs (doc-updater)

- `inputs/tools/{gene_overview,list_organisms,genes_by_metabolite,metabolites_by_gene}.yaml`:
  one example each (urea MED4 `by_evidence_source_combination`; `go_namespace=['molecular_function']`;
  mistake: "a multi-source pair is corroborated, not proven — routes share homology"; mistake:
  "go_* filters don't touch TCDB / KEGG rows").
- `references/analysis/transport.md`: "reading agreement" section points at
  `by_evidence_source_combination`; filters section names `go_namespace` / `go_evidence`.
- CLAUDE.md tool table: gbm / mbg rows mention the filters + combination rollup; gene_overview /
  list_organisms rows name the GO count (respect the row-length lint).
- `docs/backlog.md`: delete 2c.14–2c.17 when shipped; CHANGELOG `[Unreleased]` entry.

## 6. Tests (test-updater)

- Builders: new column / condition / param presence; `type(r) IN $go_gene_edge_types` in both
  GO branches when `include_ancestors=True`; pair-grouping block present in both summaries.
- API: validation (`ValueError` on unknown namespace / evidence); arm-off warning; filters threaded
  to summary, no-formula count and stereo-relative call; envelope keys + sort.
- Wrappers: new params + response fields on the Pydantic models.
- Integration (`-m kg`): the verified numbers in §3 / §4 (urea combination, MF+curated 4, MED4
  organism count 45, PMM0974 → 3); filtered ⊆ unfiltered invariant; `sum(pair_count)` = distinct
  (gene, metabolite) pairs in detail rows.
- Edge cases (`tests/integration/edge_cases/scenarios.py`): add to existing gbm / mbg scenarios —
  GO filters that empty the GO arm; filters with GO arm off (warning, no raise).
- Regression goldens move (new envelope / row keys): gbm, mbg, gene_overview, list_organisms —
  regenerate with `--force-regen` and classify the diff (additive only).
