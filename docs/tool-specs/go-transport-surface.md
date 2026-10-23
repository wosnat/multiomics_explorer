# GO transport surface (Mode B: gbm, mbg, gene_overview, list_metabolites, kg_release_info, kg_schema + docs)

**Status:** DRAFT for freeze (Phase 1 complete; awaiting user gate) · **KG:** dev build
`built_at 2026-10-19T17:03:46.14Z` (`version 0.0.0-dev`, Neo4j 5.15.0) · **Design (binding):**
`docs/superpowers/specs/2026-10-20-go-transport-surface-design.md` · **Plan:**
`docs/superpowers/plans/2026-10-23-go-transport-surface.md` · **KG note:**
`multiomics_biocypher_kg/docs/kg-changes/go-transport-substrates.md` · **Backlog:** 2c.13.

Every Cypher block below was run against the live KG at the build above ("verified against live KG
(built_at 2026-10-19T17:03:46Z)"). Every detail query was paired with its summary query for the same
inputs and `total_matching` equalled the detail row count (sum over arms) in every case listed in
§7.

## 1. Purpose

Surface the KG's GO transport route (GO term → `has primary input` → `Metabolite` / `ChemicalRole`)
next to KEGG metabolism and TCDB transport so a caller asking "what transports X in organism Y" or
"what does gene Z move" sees each route labelled, never blended. Role ids (`chebi.role:`) become
valid inputs and reach both GO and TCDB role edges. Inherited (GO is_a ancestor) rows are opt-in.

## 2. Out of scope

TCDB diamond best hit; transport direction; `gene_overview.go_transport_metabolite_count`; GO-arm
filters on `go_namespace` / gene→GO `evidence`; `list_organisms` GO-route counts; per-metabolite
`routes` agreement rollup (→ backlog 2c, one line each, per design §2). No new TCDB structure beyond
walking `Tcdb_family_transports_chemical_role`. No backward compatibility with a KG lacking slice 1.

## 3. KG facts (verified live, built_at 2026-10-19T17:03:46Z)

| Fact | Live value |
|---|---|
| GO target edges | `Molecular_function_transports_metabolite`, `Biological_process_transports_metabolite`, `Molecular_function_transports_chemical_role`, `Biological_process_transports_chemical_role`; single edge prop `go_chebi_ids` (str[]) |
| Gene→GO edges | `Gene_enables_molecular_function`, `Gene_involved_in_biological_process`; props `id, sources, evidence, evidence_score`; never >1 edge per (gene, term) |
| `r.evidence` on gene→GO edges that reach a target | `curated` 6,866 · `family_inferred` 6,770 · `domain_inferred` 203 (no other value) |
| GO term node labels | first label `Entity`; MF nodes lack the `GeneOntology` label BP nodes carry → namespace **must** come from `type(t)` |
| is_a edges | `Molecular_function_is_a_molecular_function` 3,676 · `Biological_process_is_a_biological_process` 5,680 (never cross-namespace) |
| GO role targets | 6 roles: drug 23888, neurotransmitter 25512, siderophore 26672, toxin 27026, vitamin 33229, xenobiotic 35703 |
| TCDB role edge | `Tcdb_family_transports_chemical_role` 392 edges (156 `most_specific`, 236 `inherited`) over 57 roles; props `id, substrate_depth` |
| `ChemicalRole` node | labels `[Entity, NamedThing, Attribute, ChemicalRole]`; props `id, name, level, level_kind, all_identifiers, preferred_id, *_tcdb_family_count, *transporter_count`; no `formula` / `elements` / `chebi_id` / `pathway_ids` |
| Roles with no edges at all (TCDB or GO) | 54 (e.g. `chebi.role:23357`) |
| `Schema_info.go_transport_excluded_targets` | 13 ids; **6 have a node** (`chebi:24834`, `chebi:24870`, `chebi:25213`, `chebi:36080`, `kegg.compound:C00080`, `kegg.compound:C01330`), **7 do not** (`chebi:23905`, `chebi:23906`, `chebi:24431`, `chebi:24867`, `chebi:33515`, `chebi:33694`, `chebi:51143`) |
| Direct GO rows, metabolite targets (corpus) | 12,588 rows · 7,525 gene × metabolite pairs · 4,906 genes · 198 targets |
| Direct GO rows incl. role targets (corpus) | 13,839 rows · 8,449 pairs · 5,438 genes · 204 targets |
| Direct GO rows, MED4 | 126 rows · 77 pairs · 59 genes · 45 targets (no direct role rows in MED4) |
| Organisms with genes but no GO-route gene | **none** (every organism with genes has ≥1) |
| Organism resolver caveat | `Alteromonas mediterranea AltDE` cannot be resolved by the API (every string that matches it also substring-matches `…AltDE1`; pre-existing, see Decision D12) |

## 4. Interfaces (names every later task uses)

### 4.1 Query builders (`kg/queries_lib.py`)

```python
def build_genes_by_metabolite_go_transport(
    *, metabolite_ids: list[str], organism: str,
    exclude_metabolite_ids: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    include_ancestors: bool = False,
    verbose: bool = False, limit: int | None = None, offset: int = 0,
) -> tuple[str, dict]

def build_metabolites_by_gene_go_transport(
    *, locus_tags: list[str], organism: str,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    metabolite_elements: list[str] | None = None,
    gene_categories: list[str] | None = None,
    include_ancestors: bool = False,
    verbose: bool = False, limit: int | None = None, offset: int = 0,
) -> tuple[str, dict]
```

**Note:** these §4.1 signatures supersede the task brief's interface block. The mbg GO builder
adds `metabolite_ids` and `gene_categories`, which the brief omitted (Decision D1).

- `build_genes_by_metabolite_summary` / `build_metabolites_by_gene_summary` gain
  `include_ancestors: bool = False`; `arms` accepts `"go_transport"` (default stays the caller's
  choice — api passes three arms by default); RETURN gains `rows_by_go_term_depth`
  (`[{go_term_depth, count}]`, `[]` when the GO arm is absent or matches nothing).
- `build_metabolites_by_gene_no_formula_count` gains `include_ancestors: bool = False` and accepts
  `"go_transport"` in `arms` (Decision D6).
- `build_genes_by_metabolite_transport` / `build_metabolites_by_gene_transport` (and the transport
  block of both summaries + no-formula count) walk `Tcdb_family_transports_chemical_role` too.
- `build_gene_overview` / `build_gene_overview_summary`: GO tag + widened `has_chemistry` (§6.3).
- `_list_metabolites_where` + `build_list_metabolites{,_summary}`: union organism clause, two new
  row columns, union `top_organisms` (§6.6).

### 4.2 Row keys

Added to the RETURN of **every** arm of both tools (metabolism, transport, go_transport), compact:

| Key | GO row | metabolism row | transport row |
|---|---|---|---|
| `go_term_id` | gene's own GO term (`go:0033221`) | null | null |
| `go_term_name` | `go.name` | null | null |
| `go_namespace` | `'molecular_function'` \| `'biological_process'` (from `type(t)`) | null | null |
| `go_evidence` | gene→GO `r.evidence` | null | null |
| `go_sources` | gene→GO `r.sources` (list) | null | null |
| `go_term_depth` | `0` direct; n = is_a hops (inherited) | null | null |
| `go_axiom_term_id` / `go_axiom_term_name` | term that names the target (= own term at depth 0; the ancestor when inherited) | null | null |
| `target_kind` | `'metabolite'` \| `'chemical_role'` | `'metabolite'` | `'metabolite'` \| `'chemical_role'` |

Verbose adds `go_chebi_ids` (`t.go_chebi_ids`; null on non-GO rows). On GO rows `substrate_depth`,
`tcdb_evidence_score`, `transport_substrate_resolution`, `reaction_id`, `reaction_name`,
`ec_numbers`, `mass_balance`, `tcdb_family_id`, `tcdb_family_name` and verbose
`reaction_mnxr_id`, `reaction_rhea_ids`, `tcdb_level_kind`, `tc_class_id` are null; `metabolite_*`
come from the target node (role rows: `metabolite_id` = role id, `metabolite_name` = role name,
formula / mass / chebi_id / inchikey / smiles / mnxm / hmdb null → sparse-stripped where the
existing `_GBM_SPARSE_FIELDS` rule already strips them).

`go_*` fields are **not** sparse-stripped (cross-arm fields stay explicit `None`, Phase 3 Item 6.1
rule). `go_chebi_ids` (verbose) is sparse-stripped like the other verbose ids (Decision D7).

### 4.3 API (`api/functions.py`)

- `genes_by_metabolite(..., go_include_ancestors: bool = False)`,
  `metabolites_by_gene(..., go_include_ancestors: bool = False)` → builders' `include_ancestors`.
- `_VALID_EVIDENCE_SOURCES` = `("metabolism", "transport", "metabolomics", "go_transport")`;
  `_VALID_EVIDENCE_SOURCES_GBM` = `_MBG` = `("metabolism", "transport", "go_transport")`.
  Default arms (`evidence_sources=None`) = all three, canonical order
  `("metabolism", "transport", "go_transport")`.
- Envelope (both tools) gains `rows_by_go_term_depth` **only when the GO arm is active**
  (sorted by `go_term_depth` asc). `by_evidence_source` gains `go_transport`.
  Per-entity rollup entries (`by_metabolite`, gbm `top_genes`, mbg `by_gene`, mbg
  `top_metabolites`) gain `go_transport_rows` (Decision D3).
- `_canonicalize_metabolite_ids(conn, ids, *, roles_are_targets: bool = False)`; gbm / mbg pass
  `True` (role ids kept as canonical `chebi.role:<n>`, no "not a metabolite" warning). All other
  callers keep `False` (today's warning unchanged).
- `_chemistry_input_probes` existence probe for gbm / mbg `metabolite_ids` must accept
  `ChemicalRole` ids (`MATCH (m) WHERE (m:Metabolite OR m:ChemicalRole) AND m.id IN $ids`) so a role
  id with edges is never `not_found`; a role id with no rows in the organism is `not_matched`
  (Decision D8).
- `_stereo_relatives_in_organism` passes `include_ancestors` through to the summary call so the
  "relative counts equal a re-call" invariant holds (verified §7.9).
- `_KG_IDENTITY_FIELDS` gains `"go_transport_excluded_targets"`; the gbm warning reads the list from
  the same cached path.

## 5. Sort keys

### 5.1 Builders (`ORDER BY`)

- gbm GO builder: `go_term_depth, metabolite_id, <ns_rank>, <ev_rank>, go_term_id, locus_tag`
- mbg GO builder: `go_term_depth, apoc.coll.indexOf($locus_tags, locus_tag), locus_tag, <ns_rank>,
  <ev_rank>, go_term_id, metabolite_id`
- `<ns_rank>` = `CASE go_namespace WHEN 'molecular_function' THEN 0 ELSE 1 END`;
  `<ev_rank>` = `CASE go_evidence WHEN 'curated' THEN 0 WHEN 'family_inferred' THEN 1 WHEN
  'domain_inferred' THEN 2 ELSE 3 END`.
- Existing metabolism / transport builders' ORDER BY unchanged.

### 5.2 API global keys (Mode 3 concat + sort + slice)

```python
_GO_NS_RANK = {"molecular_function": 0, "biological_process": 1}          # else 2
_GO_EVIDENCE_RANK = {"curated": 0, "family_inferred": 1, "domain_inferred": 2}  # else 3

def _gbm_sort_key(row):
    if row.get("evidence_source") == "go_transport":
        return (1, row["go_term_depth"], row.get("metabolite_id") or "",
                _GO_NS_RANK.get(row.get("go_namespace"), 2),
                _GO_EVIDENCE_RANK.get(row.get("go_evidence"), 3),
                row.get("go_term_id") or "", row.get("locus_tag") or "")
    return (0, <today's tuple: metabolite_id, evidence_source, depth_priority,
               -tcdb_evidence_score, secondary_id, locus_tag>)

def _mbg_sort_key(row, locus_index):
    if row.get("evidence_source") == "go_transport":
        lt = row.get("locus_tag") or ""
        return (3 + row["go_term_depth"], 0.0, locus_index.get(lt, len(locus_index)), lt,
                _GO_NS_RANK.get(row.get("go_namespace"), 2),
                _GO_EVIDENCE_RANK.get(row.get("go_evidence"), 3),
                row.get("go_term_id") or "", row.get("metabolite_id") or "")
    return <today's tuple>   # tiers 0 metabolism, 1 most_specific, 2 inherited
```

Resulting order: metabolism < transport most_specific < transport inherited < GO depth 0 < GO
depth 1 < … ; within GO: (gbm) metabolite_id / (mbg) input order + locus_tag, then MF before BP,
curated < family_inferred < domain_inferred, go_term_id, then locus_tag (gbm) / metabolite_id (mbg).
Keys are unique per row (GO rows are unique per gene × own term × target) — verified §7.8; each
builder's ORDER BY is the restriction of the global key to its arm, so Mode-3 over-fetch is exact.

## 6. Verified Cypher

### 6.1 GO arm detail — gbm (verified against live KG (built_at 2026-10-19T17:03:46Z))

Rendered with `include_ancestors=True, verbose=True, limit=10`; `include_ancestors=False` drops the
`UNION ALL` branch (single MATCH inside the CALL); `verbose=False` drops the ten verbose columns.
Filter conditions append to **both** branches' WHERE exactly as in the existing arms:
`(NOT (m.id IN $exclude_metabolite_ids))`, `ANY(p IN $metabolite_pathway_ids WHERE p IN
coalesce(m.pathway_ids, []))`, `g.gene_category IN $gene_categories`.

```cypher
CALL {
  MATCH (g:Gene)-[r:Gene_enables_molecular_function|Gene_involved_in_biological_process]->(go)-[t:Molecular_function_transports_metabolite|Biological_process_transports_metabolite|Molecular_function_transports_chemical_role|Biological_process_transports_chemical_role]->(m:Metabolite|ChemicalRole)
  WHERE m.id IN $metabolite_ids AND ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_name) CONTAINS word)
  RETURN g, r, go, t, m, go AS a, 0 AS go_term_depth
  UNION ALL
  MATCH (g:Gene)-[r:Gene_enables_molecular_function|Gene_involved_in_biological_process]->(go),
        p = (go)-[:Molecular_function_is_a_molecular_function|Biological_process_is_a_biological_process*1..]->(a),
        (a)-[t:Molecular_function_transports_metabolite|Biological_process_transports_metabolite|Molecular_function_transports_chemical_role|Biological_process_transports_chemical_role]->(m:Metabolite|ChemicalRole)
  WHERE m.id IN $metabolite_ids AND ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_name) CONTAINS word)
    AND NOT EXISTS { MATCH (g)-[:Gene_enables_molecular_function|Gene_involved_in_biological_process]->()-[:Molecular_function_transports_metabolite|Biological_process_transports_metabolite|Molecular_function_transports_chemical_role|Biological_process_transports_chemical_role]->(m) }
  WITH g, r, go, m, a, t, length(p) AS d
  ORDER BY d, a.id
  WITH g, r, go, m, collect({a: a, t: t, d: d})[0] AS best
  RETURN g, r, go, best.t AS t, m, best.a AS a, best.d AS go_term_depth
}
RETURN g.locus_tag AS locus_tag,
       g.gene_name AS gene_name,
       g.product AS product,
       'go_transport' AS evidence_source,
       null AS substrate_depth,
       null AS tcdb_evidence_score,
       null AS transport_substrate_resolution,
       null AS reaction_id,
       null AS reaction_name,
       null AS ec_numbers,
       null AS mass_balance,
       null AS tcdb_family_id,
       null AS tcdb_family_name,
       m.id AS metabolite_id,
       m.name AS metabolite_name,
       m.formula AS metabolite_formula,
       m.mass AS metabolite_mass,
       m.chebi_id AS metabolite_chebi_id,
       go.id AS go_term_id,
       go.name AS go_term_name,
       CASE WHEN type(t) STARTS WITH 'Molecular_function' THEN 'molecular_function' ELSE 'biological_process' END AS go_namespace,
       r.evidence AS go_evidence,
       r.sources AS go_sources,
       go_term_depth,
       a.id AS go_axiom_term_id,
       a.name AS go_axiom_term_name,
       CASE WHEN m:ChemicalRole THEN 'chemical_role' ELSE 'metabolite' END AS target_kind,
       g.gene_category AS gene_category,
       m.inchikey AS metabolite_inchikey,
       m.smiles AS metabolite_smiles,
       m.mnxm_id AS metabolite_mnxm_id,
       m.hmdb_id AS metabolite_hmdb_id,
       null AS reaction_mnxr_id,
       null AS reaction_rhea_ids,
       null AS tcdb_level_kind,
       null AS tc_class_id,
       t.go_chebi_ids AS go_chebi_ids
ORDER BY go_term_depth, metabolite_id, CASE go_namespace WHEN 'molecular_function' THEN 0 ELSE 1 END, CASE go_evidence WHEN 'curated' THEN 0 WHEN 'family_inferred' THEN 1 WHEN 'domain_inferred' THEN 2 ELSE 3 END, go_term_id, locus_tag
LIMIT $limit
```

Params: `{metabolite_ids, organism[, exclude_metabolite_ids, metabolite_pathway_ids,
gene_categories][, offset][, limit]}` (SKIP before LIMIT, as in the peer builders).

Inherited-branch semantics (design §3.3, measured §7.2):
- **Dedup** — the `NOT EXISTS` drops any (gene, target) the gene reaches directly through GO
  (depth 0, any own term). TCDB / KEGG are never consulted.
- **Grain** — one row per (gene, own term, target) at the minimum is_a hop count; among equal-depth
  ancestors the lowest `a.id` is the axiom term (deterministic; Decision D4).
- **Min-depth pick** — relies on `ORDER BY d, a.id` followed by `collect(...)[0]`. Implementers may
  use an explicit `min(d)` form instead if it reproduces the verified counts in §7.2 / §7.7.
- Shared filters bind `g` / `m` only, so they apply identically to the direct check and the
  inherited rows.

### 6.2 GO arm detail — mbg (verified against live KG (built_at 2026-10-19T17:03:46Z))

Identical body and RETURN to §6.1 with the anchor and filters swapped:

```cypher
-- first WHERE (both branches):
WHERE g.locus_tag IN $locus_tags AND ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_name) CONTAINS word)
  [AND m.id IN $metabolite_ids]
  [AND (NOT (m.id IN $exclude_metabolite_ids))]
  [AND ALL(elem IN $metabolite_elements WHERE elem IN coalesce(m.elements, []))]
  [AND ANY(p IN $metabolite_pathway_ids WHERE p IN coalesce(m.pathway_ids, []))]
  [AND g.gene_category IN $gene_categories]
...
ORDER BY go_term_depth, apoc.coll.indexOf($locus_tags, locus_tag), locus_tag, CASE go_namespace WHEN 'molecular_function' THEN 0 ELSE 1 END, CASE go_evidence WHEN 'curated' THEN 0 WHEN 'family_inferred' THEN 1 WHEN 'domain_inferred' THEN 2 ELSE 3 END, go_term_id, metabolite_id
```

`metabolite_elements` drops role rows (no `elements`) and formula-less classes (carbohydrate,
Lipid, amino-acid zwitterion, …), as it does formula-less metabolites today.

### 6.3 Existing arms — widened (verified against live KG (built_at 2026-10-19T17:03:46Z))

Transport arm, detail + summary + no-formula count, both tools:

```cypher
MATCH (g:Gene)-[gt:Gene_has_tcdb_family]->(tf:TcdbFamily)-[r:Tcdb_family_transports_metabolite|Tcdb_family_transports_chemical_role]->(m:Metabolite|ChemicalRole)
WHERE ... AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family]->(d:TcdbFamily) WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(tf) }
```

(`TCDB_DEEPEST_ATTACHMENT_PREDICATE` unchanged; the role edge carries `substrate_depth` so the
existing `substrate_depth` filter and the depth-tier sort apply to role rows too.)

Both existing detail arms append after `m.chebi_id AS metabolite_chebi_id`:

```cypher
       null AS go_term_id, null AS go_term_name, null AS go_namespace, null AS go_evidence,
       null AS go_sources, null AS go_term_depth, null AS go_axiom_term_id, null AS go_axiom_term_name,
       'metabolite' AS target_kind                                                    -- metabolism
       CASE WHEN m:ChemicalRole THEN 'chemical_role' ELSE 'metabolite' END AS target_kind  -- transport
-- verbose: , null AS go_chebi_ids
```

### 6.4 Summary — gbm, three arms (verified against live KG (built_at 2026-10-19T17:03:46Z))

Deltas against today's `build_genes_by_metabolite_summary` (mbg's summary takes the same deltas;
its `by_gene` / `top_metabolites` get `go_transport_rows`, `by_element` / `top_metabolite_pathways`
need no change — GO rows carry `metabolite_elements` / `metabolite_pathway_ids` like any row):

1. Every arm's RETURN gains two columns so `UNION` (distinct) never collapses two GO rows of one
   (gene, target) via different terms: metabolism / transport `..., null AS go, null AS gdepth`.
2. Transport arm walks the role edge (§6.3).
3. GO arm block (emitted when `"go_transport" in arms`; inner CALL = §6.1 body,
   `include_ancestors` switches the `UNION ALL` branch):

```cypher
  UNION
  CALL {
    MATCH (g:Gene)-[r:Gene_enables_molecular_function|Gene_involved_in_biological_process]->(go)-[t:Molecular_function_transports_metabolite|Biological_process_transports_metabolite|Molecular_function_transports_chemical_role|Biological_process_transports_chemical_role]->(m:Metabolite|ChemicalRole)
    WHERE m.id IN $metabolite_ids AND ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_name) CONTAINS word)
    RETURN g, r, go, t, m, go AS a, 0 AS go_term_depth
    [UNION ALL <inherited branch of §6.1, same WHERE>]
  }
  RETURN g, null AS r, null AS tf, m, 'go_transport' AS es,
         null AS sdepth, null AS tscore,
         go, go_term_depth AS gdepth
}
WITH g, r, tf, m, es, sdepth, tscore, go, gdepth
```

4. The `rows` collect map gains `go_term_depth: gdepth`.
5. Per-entity rollups gain, after `transport_inherited_rows`:
   `go_transport_rows: size([row IN rows WHERE row.metabolite_id = mid AND row.es = 'go_transport'])`
   (gbm `by_metabolite`; `row.locus_tag = lt` in gbm `top_genes`; same in mbg `by_gene` /
   `top_metabolites`).
6. Final RETURN gains (rows is in scope there in both builders):

```cypher
       [d IN apoc.coll.toSet([row IN rows WHERE row.es = 'go_transport' | row.go_term_depth]) |
          {go_term_depth: d, count: size([row IN rows WHERE row.es = 'go_transport' AND row.go_term_depth = d])}] AS rows_by_go_term_depth
```

`count(DISTINCT tf)` / `count(DISTINCT r)` ignore GO rows (null) — `transporter_count_total`,
`reaction_count_total`, `top_reactions`, `top_tcdb_families`, `rows_by_substrate_depth` are
untouched by GO rows (anti-goal: no blending). When only the GO arm is selected the UNION has the GO
block alone.

`build_metabolites_by_gene_no_formula_count` gets items 1–3 with
`size(coalesce(m.elements, [])) = 0` appended to the GO arm's WHERE (both branches). Verified:
MED4 60-gene set (§7.7), GO arm only → 22 rows / 12 targets (direct), 75 rows / 21 targets
(`include_ancestors=True`).

### 6.5 `gene_overview` (verified against live KG (built_at 2026-10-19T17:03:46Z))

`build_gene_overview` — `evidence_sources` gets a fourth CASE after the `metabolomics` one
(`metabolomics` stays KEGG / TCDB-derived):

```cypher
  CASE WHEN EXISTS {
    MATCH (g)-[:Gene_enables_molecular_function|Gene_involved_in_biological_process]->()-[:Molecular_function_transports_metabolite|Biological_process_transports_metabolite|Molecular_function_transports_chemical_role|Biological_process_transports_chemical_role]->()
  } THEN ['go_transport'] ELSE [] END
```

`build_gene_overview_summary` — `has_chemistry` gains `OR EXISTS { <same pattern> }`.
Tag order in `evidence_sources`: metabolism, transport, metabolomics, go_transport.

### 6.6 `list_metabolites` (verified against live KG (built_at 2026-10-19T17:03:46Z))

```cypher
-- _list_metabolites_where, organism clause:
ANY(o IN coalesce(m.organism_names, []) + coalesce(m.go_transport_organism_names, []) WHERE toLower(o) IN $organism_names_lc)
-- build_list_metabolites_summary, all_orgs (both branches):
apoc.coll.flatten(collect(apoc.coll.toSet(coalesce(m.organism_names, []) + coalesce(m.go_transport_organism_names, [])))) AS all_orgs
-- build_list_metabolites RETURN adds:
m.go_transport_organism_names AS go_transport_organism_names,
m.go_transport_organism_count AS go_transport_organism_count
```

`apoc.coll.toSet` per metabolite keeps an organism on both lists counted once in `top_organisms`.

## 7. Test expectations (live numbers, built_at 2026-10-19T17:03:46Z)

"parity" = Σ detail rows over the selected arms == summary `total_matching` (true in every row).

### 7.1 Step 1 — gbm GO arm direct, urea MED4

`genes_by_metabolite(["kegg.compound:C00086"], "Prochlorococcus MED4")`:

| Measure | Value |
|---|---|
| GO rows | **11** over PMM0970–PMM0974 (urtA–urtE): urtA 2, urtB 2, urtC 2, urtD 2, urtE 3 |
| urtA PMM0970 | `go:0033221` MF curated `['ncbi']`; `go:0015840` BP curated `['cyanorak','ncbi']` |
| other terms | `go:0071918` "urea transmembrane transport" (BP) on urtB, urtE |
| `go_chebi_ids` (verbose) | `['CHEBI:16199']` on all 11 |
| all arms | metabolism 4 · transport 30 · go_transport 11 → `total_matching` **45**; `gene_count_total` 29; `transporter_count_total` 3; `rows_by_go_term_depth` `[{0, 11}]` |
| `go_include_ancestors=True` | unchanged (45; urea reached directly by all GO genes) |
| first GO row (global sort) | index 34 = after all 34 metabolism + TCDB rows |

### 7.2 Step 2 — inherited branch (metabolite targets; design §3.3 numbers)

| Measure | Corpus | MED4 |
|---|---|---|
| inherited-only (gene, target) pairs | **4,194** | **53** |
| genes with ≥1 inherited pair | 1,897 | **28** |
| genes with **no direct GO path to a Metabolite** that gain one by inheritance | **379** | 2 |
| inherited rows (gene × own term × target) | 6,069 | 71 |
| pair min-depth histogram | 1: **2,709** · 2: **1,186** · 3: **241** · ≥4: **58** | 1: 41 · 2: 11 · 3: 1 |

Including role targets: corpus 4,292 pairs / 6,210 rows / 1,922 genes (role pairs 98); MED4 55
pairs / 74 rows / 29 genes. "379" is the metabolite-only measure (genes with no direct path to any
target incl. roles: 105).

**Test expectation:** tests assert **379** only. It counts genes that reach a *Metabolite* only by
inheritance (no direct GO path to any Metabolite). The roles-included figure, 105, is for reference
and no test asserts it.

murJ: `metabolites_by_gene(["PMM0261"], "Prochlorococcus MED4", go_include_ancestors=True)` →
one GO row `kegg.compound:C01356` Lipid, `go_term_id go:0034204` "lipid translocation",
`go_term_depth 1`, `go_axiom_term_id go:0006869`, `go_axiom_term_name "lipid transport"`
(+ 3 TCDB rows; total 4). Default call: **0** GO rows (3 TCDB rows).

### 7.3 Step 3 — role arms

| Call (builder level) | GO | TCDB | total |
|---|---|---|---|
| `chebi.role:26672`, organism string `Alteromonas mediterranea AltDE` — **do not use as a test input** (Decision D12) | 60 (= 28 AltDE + 32 AltDE1, word-match leak) incl. **MADE_1013240** `go:0015891` "siderophore transport" BP curated `['ncbi']` | 188 (92 + 96) | 248 |
| same, AltDE genes only (`g.organism_name =`) | **28 rows / 24 genes** | **92 rows / 85 genes** | 120 |
| `chebi.role:26672`, `Alteromonas mediterranea AltDE1` (API-resolvable; **the test input**, D12) | **32** (incl. `amad1_16875` `go:0015891` BP curated `['ncbi']`) | **96** | 128 · genes 112 · `transporter_count_total` 6 |
| `chebi.role:26672`, `Prochlorococcus MED4` | **0** (empty-GO case) | **25 rows / 23 genes**, all `inherited` | 25 |
| `chebi.role:25512` (neurotransmitter), `Pseudomonas putida KT2440` | 5 | 65 | 70 |

All role rows: `target_kind='chemical_role'`, `metabolite_name` = role name, formula null,
`go_chebi_ids ['CHEBI:26672']`.

Mixed batch `["chebi.role:26672", "kegg.compound:C00086"]`, `Alteromonas mediterranea AltDE1`:
metabolism 2 · transport 169 · GO 32 → **203**; both `target_kind` values present (urea rows are
TCDB / KEGG in AltDE1 — AltDE1 has no urea GO rows). Same + `exclude_metabolite_ids=
["chebi.role:26672"]` → **75** (metabolism 2, transport 73, GO 0).

mbg TCDB role rows move TCDB rollups (intended, design decision 5): `PMM0097` (tolC, MED4)
transport-only `total_matching` **535 → 572** (+37 role rows), `rows_by_substrate_depth`
most_specific 217 → 242, inherited 318 → 330, `transporter_count_total` 2 → 2. 53 MED4 genes carry
a deepest TCDB role edge.

### 7.4 Step 4 — mbg GO arm, PMM0970

`metabolites_by_gene(["PMM0970"], "Prochlorococcus MED4")`: **6** rows = 4 TCDB
(`C00086` via `tcdb:3.A.1.4.4` and `tcdb:3.A.1.4.5`, `C07044` Hydroxyurea, `C14415` Thiourea; all
most_specific) **then** 2 GO (`go:0033221` MF, then `go:0015840` BP, both urea, depth 0).
`metabolite_count_total` 3; `rows_by_evidence_source` `{transport 4, go_transport 2}`.
With `go_include_ancestors=True` (GO arm only): 3 rows — the 2 above + `chebi:64708` "one-carbon
compound" via own term `go:0015840`, axiom `go:0019755` "one-carbon compound transport", depth 1.

### 7.5 Step 5 — summaries

Parity held for every case in §7.1–§7.9. `rows_by_evidence_source` carries `go_transport`
whenever GO rows exist (e.g. urea MED4 `[metabolism 4, transport 30, go_transport 11]`).

### 7.6 Step 6 — pass-throughs

| Measure | Value |
|---|---|
| MED4 genes tagged `go_transport` in `gene_overview.evidence_sources` | **59** (run on the real builder with §6.5 injected; same with or without target labels) |
| MED4 genes whose only tag is `go_transport` | 2: `PMM0533` (aar), `PMM0866` (lptC) |
| MED4 `has_chemistry` over all 1,973 genes | **786 → 788** (+2, the two above); corpus GO-only genes 220 |
| corpus genes tagged `go_transport` | 5,438 |
| `list_metabolites(organism_names=['Prochlorococcus MED4'])` `total_matching` | **1,883 → 1,891** (+8 GO-only); 45 MED4 metabolites carry MED4 in `go_transport_organism_names` |
| `top_organisms` MED4 count under that filter | 1,883 → 1,891 |
| corpus metabolites with `go_transport_organism_names` | 198; with `evidence_sources ∋ go_transport` 208; GO-only (organism_count 0) 31 |
| `list_metabolites(evidence_sources=['go_transport'])` | 208 |
| `evidence_sources=['go_transport']` + MED4 (union clause) | 165 (metabolite-level filters are independent: GO edge anywhere AND organism on either list) |

### 7.7 Step 7 — shared filters on the GO arm (GO arm only; MED4)

mbg input: the 59 MED4 GO-route genes + PMM0261 (60 tags). gbm input: `["kegg.compound:C00086",
"kegg.compound:C00009", "kegg.compound:C00238", "kegg.compound:C01356", "chebi:16646"]`.

| Tool | Filter | ancestors | GO rows | genes | targets |
|---|---|---|---|---|---|
| mbg | none | F | 126 | 59 | 45 |
| mbg | `gene_categories=['Transport']` | F | 40 | 23 | 20 |
| mbg | `metabolite_pathway_ids=['kegg.pathway:ko02010']` | F | 58 | 26 | 15 |
| mbg | `exclude_metabolite_ids=['kegg.compound:C00086']` | F | 115 | 57 | 44 |
| mbg | `metabolite_elements=['N']` | F | 43 | 21 | 12 |
| mbg | `metabolite_ids=['kegg.compound:C00086']` | F | 11 | 5 | 1 |
| mbg | none | T | 199 (depths 0:126 1:52 2:18 3:2 4:1; role rows present) | 60 | 60 |
| mbg | `exclude_metabolite_ids=['kegg.compound:C01356']` | T | 191 | 58 | 59 |
| mbg | `metabolite_elements=['N']` | T | 46 (0:43 1:3; no role rows) | 23 | 13 |
| gbm | none | F | 33 | 17 | 5 |
| gbm | `gene_categories=['Transport']` | F | 6 | 6 | 3 |
| gbm | `metabolite_pathway_ids=['kegg.pathway:ko02010']` | F | 25 | 9 | 2 |
| gbm | `exclude_metabolite_ids=['kegg.compound:C00086']` | F | 22 | 12 | 4 |
| gbm | none | T | 45 (0:33 1:12) | 25 | 5 |
| gbm | `exclude_metabolite_ids=['kegg.compound:C01356']` | T | 37 (0:32 1:5) | 19 | 4 |

**No filter is a no-op on the GO arm**: each shared filter changes the result. Arm-scoped filters
(`ec_numbers`, `mass_balance`, `substrate_depth`) are not passed to the GO builders (they don't
accept them — `TypeError`, same rule as today's per-arm scope), so they are documented no-ops on GO
rows.

### 7.8 Paging (three-arm Mode-3 continuity, §5.2)

Mode-3 simulation with the §5.2 keys (per-arm builders with `LIMIT limit+offset`, concat, sort,
slice): gbm urea MED4, `limit=10` → pages concatenate to exactly the full sorted 45 rows; first GO
row at index 34, last non-GO at 33. mbg `["PMM0970","PMM0261"]`, `go_include_ancestors=True`,
`limit=3` → 11 rows, pages exact, first GO at index 7. Sort keys unique per row in both.

### 7.9 Edge cases

| Case | Inputs | Result |
|---|---|---|
| excluded target with node | `C00080` (H⁺) MED4 | GO 0 · metabolism 250 · transport 131 → 381; warning fires |
| excluded target with node | `C01330` (Na⁺) MED4 | GO 0 · transport 71; warning fires |
| excluded target, no node | `chebi:23906` MED4 | `not_found.metabolite_ids` + warning (no node exists — confirmed) |
| empty GO arm (Decision D13) | `chebi.role:26672` in MED4 (no organism lacks GO-route genes) | GO 0 · TCDB 25; envelope keys present. Also: PMM0261 default mbg (GO 0) |
| role id with no edges | e.g. `chebi.role:23357` (54 such roles) | 0 rows; `not_matched` (Decision D8) |
| ancestors on a gene with none to add | `PMM0085` (ktrA) MED4 | identical rows with/without `go_include_ancestors` (32 of 59 MED4 GO genes behave so) |
| stereo relative counts | `kegg.compound:C00025` → relative `C00302` (Glutamate) MED4 | by_metabolite rows 30 → 31 (`go_transport_rows` 1), gene_count 30 = re-call |
| performance | gbm 4 broad targets KT2440 ancestors (625 rows); mbg 2,000 KT2440 genes ancestors (832 GO rows) | ~1.8 s wall each incl. Python start-up |

## 8. Warnings (exact copy; api layer, plan Task 4b)

- Excluded target (gbm only; GO arm active; requested canonical id ∈
  `Schema_info.go_transport_excluded_targets`), one per id:
  `"'{id}' is excluded from the GO transport route by curation (coupling ion or upper-level class) — an empty GO answer is not biology; TCDB rows still answer."`
- Neurotransmitter (gbm when `chebi.role:25512` is an input; mbg when a returned row carries it):
  `"chebi.role:25512 (neurotransmitter) on the GO route is mostly bacterial NSS amino-acid transporters, not neurotransmitter transport."`

Both fire only when the GO arm is active (Decision D9). The excluded-target warning also fires for
the 7 ids with no node, alongside `not_found`.

## 9. Decisions (made in Phase 1)

- **D1** mbg GO builder takes `metabolite_ids` and `gene_categories` in addition to the brief's
  signature. The existing mbg arms take both; without them a `metabolite_ids` / `gene_categories`
  call would leak unfiltered GO rows. Both verified to narrow (§7.7). Brief vs. design: the design
  lists `gene_categories` as a shared filter, so the design wins. Accepted at task review.
- **D2** One builder per tool, inherited rows inside the same builder as a `UNION ALL` branch of an
  inner `CALL` (not a separate builder); emitted only when `include_ancestors=True`, so the default
  query has no is_a walk.
- **D3** Per-entity rollup entries gain `go_transport_rows` (so `rows` = metabolism + transport
  tiers + GO). Not a new envelope key (design: "no new envelope keys except §3.3's").
- **D4** Inherited row axiom = ancestor at minimum is_a hops; ties broken by lowest `a.id`.
- **D5** gbm GO rows sort by `go_term_depth` first (direct before inherited across all metabolites),
  then the design's within-GO order. Design states depth-first only for mbg; applied to gbm too so
  coarser inherited rows never interleave with direct ones.
- **D6** `build_metabolites_by_gene_no_formula_count` covers the GO arm and TCDB role rows; role
  rows count as "no formula" (they have none), so `rows(unfiltered) = rows(filtered) +
  no_formula_excluded + element mismatches` stays true.
- **D7** `go_chebi_ids` (verbose) joins the sparse-strip set; the eight compact `go_*` fields and
  `target_kind` never strip.
- **D8** gbm / mbg existence probe accepts `ChemicalRole`; a role id with no rows is `not_matched`,
  not `not_found`.
- **D9** Both warnings require the GO arm active (`evidence_sources` includes `go_transport` or is
  None).
- **D10** `rows_by_go_term_depth` is always in the summary RETURN; the api emits it only when the GO
  arm is active.
- **D11** Transport-arm TCDB role rows: `metabolite_count_total` / `by_gene.metabolite_count` count
  role targets too (they are distinct targets). The old mbg docstring claim "distinct metabolites
  across transport rows equal `transported_metabolite_count`" now holds only over
  `target_kind='metabolite'` rows — update the docstring.
- **D12** (controller ruling; replaces Q1) Integration tests that need an Alteromonas strain use
  the exact strain `Alteromonas mediterranea AltDE1`: 32 GO siderophore rows, plus the mixed batch
  203 and the role-excluded batch 75 (§7.3). `Alteromonas mediterranea AltDE` is ambiguous with AltDE1
  in the existing organism resolver, and the builders' word match leaks AltDE1 genes. This is pre-existing
  and not GO-specific. The resolver fix goes to the backlog and is not part of this change. MADE_1013240
  stays a spec observation (§7.3) and is not a test input.
- **D13** (controller ruling; replaces Q2) No organism lacks GO-route genes. The empty-GO-arm edge
  scenario (`gbm_go_arm_empty_organism`) uses siderophore `chebi.role:26672` in
  `Prochlorococcus MED4`: 0 GO rows, 25 TCDB rows, envelope keys present.

## 10. Open questions for the user (all resolved — spec FROZEN 2026-10-23)

Q1 and Q2 were resolved by D12 and D13.

- **Q3** resolved (user, 2026-10-23): `has_chemistry` / the gene_overview `transport` tag stay TCDB→Metabolite only; the 29 genes with only a deepest TCDB role edge are a backlog item for the TCDB redesign.

## 11. Implementation order (Mode B, plan Tasks 3–4)

| Step | Layer | File | What |
|---|---|---|---|
| 1 | Query builders | `kg/queries_lib.py` | §4.1, §6 |
| 2 | API | `api/functions.py` | §4.3, §5.2, §8, `kg_schema` edge descriptions, `_KG_IDENTITY_FIELDS` |
| 3 | Config | `config/edge_descriptions.yaml`, `config/schema_baseline.yaml` | four caveat paragraphs; 4 GO edges + `Tcdb_family_transports_chemical_role` required |
| 4 | MCP | `mcp_server/tools.py` | `GeneReactionMetaboliteTriplet` 9 fields + verbose `go_chebi_ids`; `go_include_ancestors`; `Literal`s; `rows_by_go_term_depth`; `MetaboliteResult.go_transport_organism_*`; kg_release_info + kg_schema models |
| 5 | Tests | unit + kg + scenarios | numbers in §7 |
| 6 | Docs | YAMLs, `analysis/transport.md`, `analysis/metabolites.md`, CLAUDE.md, `kg_claims.yaml` | design §3.8 |
