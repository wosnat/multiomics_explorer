# GO transport surface — design

**Date:** 2026-10-20 · **Backlog:** 2c.13 · **KG side:** built on the dev graph
(`multiomics_biocypher_kg/docs/kg-changes/go-transport-substrates.md`, built 2026-10-18T18:40Z,
absorbed in explorer commit f0bceeb) · **Dialog:**
`docs/kg-specs/2026-10-18-go-transport-substrates-explorer-asks.md` (TPS-001..008, R1–R5, F1–F4).

## 1. Intent

The KG now carries a second, independent transport route: GO transport terms whose logical
definition names a substrate (`has primary input`) are linked to the same `Metabolite` /
`ChemicalRole` nodes TCDB, KEGG and metabolomics use. The explorer surfaces it so an LLM asking
"what transports X in organism Y" or "what does gene Z move" sees the GO route **side by side** with
TCDB and KEGG, each row labelled with its route, and the routes never blended into one flag or
count. Agreement between routes is the confident core; disagreement is few enough to inspect.

Ships as a joint release: an explorer MCP release that surfaces the GO arm, then the KG release
carrying slice 1 raises `mcp_min_version` to it.

**Context for the builder.** A large TCDB / transport redesign on the KG side follows this release
(programme project 3; will likely retire `substrate_depth`, `substrate_breadth`,
`transport_substrate_resolution`). Do not build new TCDB-specific structure here beyond what §3.5
names; keep the GO arm self-contained so it survives that redesign.

## 2. Goals, non-goals, anti-goals

**Goals**
- GO rows appear **by default** in `genes_by_metabolite` (gbm) and `metabolites_by_gene` (mbg).
- `chebi.role:` inputs reach both GO and TCDB role edges.
- The GO route is discoverable in `gene_overview`, `list_metabolites`, `list_filter_values`,
  `kg_release_info`, `kg_schema`.
- Every surface that shows GO rows carries the route caveat (term definition ≠ gene fact; BP is
  broader than MF; filtered targets are empty by curation).

**Non-goals (this release; backlog)**
- TCDB diamond best hit (`Gene_has_tcdb_family.best_hit_*`) — out of explorer scope.
- Transport direction (no data).
- `gene_overview.go_transport_metabolite_count`; GO-arm filters `go_namespace` / gene→GO
  `evidence`; `list_organisms` GO-route counts; per-metabolite `routes` agreement rollup.
  → add to `docs/backlog.md` as items under 2c (one line each).
- Backlog 2c.5 / 2c.7 / 2c.9 (held for the TCDB redesign).

**Anti-goals (a failure even if it works)**
- Blending: a GO row must never change `transport` rows, `substrate_depth`, `tcdb_*`,
  `transporter_gene_count`, `catalyst_gene_count`, `organism_count` or `transport_substrate_resolution`.
- Presenting a GO row as a gene-level transport fact. The row says "this gene carries a GO term
  that GO defines as moving X"; whether the gene deserves the term is `go_evidence` / `go_sources`.
- Inherited (ancestor-term) GO rows appearing without the caller asking for them.

## 3. What gets built

### 3.1 `genes_by_metabolite` and `metabolites_by_gene` — the `go_transport` arm

New arm, path:

```
(g:Gene)-[r:Gene_enables_molecular_function|Gene_involved_in_biological_process]->(go)
        -[t:Molecular_function_transports_metabolite|Biological_process_transports_metabolite]->(m:Metabolite)
```

plus, for role targets, `…_transports_chemical_role` → `(cr:ChemicalRole)` (§3.2).
Single organism, same organism scoping as the other arms. Note the GO term node's first label is
`Entity`; read the namespace from `type(t)` (MF vs BP edge), not `labels(go)[0]`.

**Default arms** (`evidence_sources=None`): `metabolism`, `transport`, `go_transport` (decided).
`_VALID_EVIDENCE_SOURCES_GBM` / `_MBG` and the MCP `Literal`s gain `go_transport`.
Mode 1 (single arm) / Mode 3 (multi-arm over-fetch + concat + global sort + slice) extend to three
arms.

**Row grain:** one row per gene × GO term × target (decided — long format). urtA × urea is 2 GO
rows (MF `go:0033221` and BP `go:0015840`) next to its 2 TCDB rows. Corpus: 12,588 direct rows over
7,525 gene × metabolite pairs; MED4 126 rows / 59 genes / 45 metabolites.

**Row fields.** Same row class as today (polymorphic; fields of other arms explicitly `null`). New
fields, present on every row of both tools (null on non-GO rows):

| Field | GO row value |
|---|---|
| `go_term_id` | the gene's own GO term (`go:0033221`) |
| `go_term_name` | `ATPase-coupled urea transmembrane transporter activity` |
| `go_namespace` | `molecular_function` \| `biological_process` (from the edge type) |
| `go_evidence` | gene→GO edge `r.evidence` (`curated` / `family_inferred` / `domain_inferred`) |
| `go_sources` | gene→GO edge `r.sources` (list) |
| `go_term_depth` | `0` for direct rows; n = is_a hops for inherited rows (§3.3) |
| `go_axiom_term_id`, `go_axiom_term_name` | the term that names the substrate: equals `go_term_*` when depth 0; the ancestor when inherited |
| `target_kind` | `metabolite` \| `chemical_role` (on all rows; TCDB/KEGG metabolite rows = `metabolite`) |
| verbose: `go_chebi_ids` | `t.go_chebi_ids` (ChEBI id(s) as GO states them, before canonicalisation) |

On GO rows: `substrate_depth`, `tcdb_evidence_score`, `transport_substrate_resolution`,
`tcdb_family_*`, `reaction_*`, `ec_numbers`, `mass_balance` are `null`. `metabolite_*` fields are
filled from the target node.

Real example rows (live KG) are in the design dialog; the builder regenerates them for the YAML.

**Sort.** gbm and mbg global sort places GO rows **after** all metabolism and TCDB rows (mbg today:
metabolism → most_specific → inherited; append go_transport depth 0, then inherited GO by
`go_term_depth`). Within GO: metabolite_id (gbm) / locus_tag (mbg), MF before BP, `go_evidence`
curated → family_inferred → domain_inferred, `go_term_id`, locus_tag / metabolite_id.

**Filters.** Arm-scoped filters keep today's per-arm rule: `ec_numbers` / `mass_balance`
(metabolism) and `substrate_depth` (TCDB) do not apply to the GO arm — the GO arm treats them
exactly as the transport arm treats `ec_numbers`. Shared filters apply to the GO arm:
`gene_categories`, `metabolite_pathway_ids`, `exclude_metabolite_ids`, mbg `metabolite_elements`.

**Envelope.** GO rows count in every existing rollup that counts rows or distinct genes /
metabolites: `total_matching`, `rows_by_evidence_source` / `by_evidence_source` (gains
`go_transport`), `by_metabolite`, `by_gene`, `top_genes`, `top_metabolites`,
`top_metabolite_pathways`, `by_element`, `gene_count_total`, `metabolite_count_total`.
TCDB-only rollups (`by_substrate_depth`, `top_tcdb_families`, `transporter_count_total`) and
`top_reactions` are untouched. `stereo_relatives` counts stay TCDB/KEGG-defined (they mirror a
re-call's `by_metabolite` today — if `by_metabolite` now includes GO, extend the relative's counts
the same way so the "equals a re-call" invariant holds; builder verifies). No new envelope keys
except §3.3's.

**Filtered-target warning.** When the GO arm is active and a requested target id (after
canonicalisation) is in `Schema_info.go_transport_excluded_targets`, add a warning: the GO route
returns nothing for it by curation (coupling ions / upper-level classes), not biology; TCDB rows
still answer. 6 of the 13 ids are nodes (H⁺ `kegg.compound:C00080`, Na⁺ `C01330`, ion, metal cation,
inorganic anion, protein); the other 7 have no node — a caller passing one also gets `not_found`,
and the warning still fires. Read the list via the same cached path `kg_release_info` uses (§3.6).

### 3.2 Role inputs reach role edges (GO and TCDB)

Today a `chebi.role:` input stays in `not_found` with a warning pointing to `run_cypher`.
After: role ids are valid gbm inputs. GO arm walks `…_transports_chemical_role`; the **transport
arm also walks `Tcdb_family_transports_chemical_role`** (decided; 392 edges / 57 roles; edge carries
`substrate_depth`, same deepest-attachment predicate as the metabolite edge). Role rows carry
`target_kind = 'chemical_role'`, `metabolite_id` = the role id, `metabolite_name` = role name,
chemistry fields null. Live reach: xenobiotic 443 genes, siderophore 305, drug 120,
neurotransmitter 24, vitamin 19, toxin 13 (GO).

- **mbg returns role rows from both routes** (GO and TCDB) for the gene, `target_kind`
  distinguishing them. TCDB role rows are transport rows: they count in `by_substrate_depth`,
  `top_tcdb_families`, `transporter_count_total` — so mbg TCDB rollups move for genes with TCDB
  role edges. This is an intended TCDB-side change (decision 5), not GO blending; record it in the
  CHANGELOG. `metabolite_elements` drops role rows (no formula), as it does formula-less
  metabolites today. The metabolism arm has no role edges.
- **Role ids as inputs:** valid in gbm `metabolite_ids` and in gbm / mbg `exclude_metabolite_ids`.
  `_canonicalize_metabolite_ids` gets a per-call switch (e.g. `roles_are_targets: bool`): gbm / mbg
  pass True (role ids pass through as canonical, no "not a metabolite" warning); every other tool
  sharing the helper (`list_metabolites`, assay tools) keeps today's warning unchanged.
- **Warnings:** the neurotransmitter-role caveat fires in gbm when `chebi.role:25512` is an input,
  and in mbg when a returned row carries it. The excluded-target warning (§3.1) fires in gbm only
  (mbg takes no target input).

### 3.3 Inherited GO rows — opt-in (decided: option B)

The KG attaches a substrate only to the term whose own axiom names it. A gene annotated with a
descendant term logically inherits its ancestors' substrates (is_a). Measured: +4,194 gene ×
metabolite pairs over the 7,525 direct (82% generic classes — carboxylic acid anion, organic acid,
carbohydrate, lipid; iron cation 485 genes is the main defined target); depth 1: 2,709, 2: 1,186,
3: 241, ≥4: 58; 379 genes reach a GO substrate only this way (MED4 `murJ` "lipid translocation" →
Lipid; PMM1173 "sugar transmembrane transporter activity" → carbohydrate). MED4 +53 pairs / 28 genes.

- New parameter on gbm and mbg: `go_include_ancestors: bool = False`.
- When True, the GO arm also returns rows reached through
  `(go)-[:Molecular_function_is_a_molecular_function|Biological_process_is_a_biological_process*1..]->(a)-[t]->(target)`,
  marked `go_term_depth = min hops`, `go_axiom_term_*` = the ancestor `a`. **Dedup rule:** an
  inherited row is emitted only for a (gene, target) pair the gene does **not** already reach
  directly through GO (depth 0, any of its terms); TCDB / KEGG rows are not consulted (no blending).
  Among the gene's own terms reaching that target by inheritance, one row per (gene, own term,
  target) at its minimum depth. This is the rule behind the measured +4,194 pairs / 379 genes.
- Envelope gains `rows_by_go_term_depth` (`[{go_term_depth, count}]`) only when the GO arm is active.
- Doc: inherited rows answer class questions ("what transports amino acids / carbohydrates"); they
  are coarser; direct-only is the default and matches the KG's organism rollups.
- `gene_overview` and `list_metabolites` stay direct-only (match the KG precompute).

### 3.4 `gene_overview`

Per-gene `evidence_sources` gains `go_transport` when a direct path
Gene → GO term → (Metabolite | ChemicalRole) exists, via the same CASE/EXISTS pattern as the
other routes. The `metabolomics` tag stays derived from KEGG/TCDB paths only (no blending).
`has_chemistry` (`queries_lib.py` ~1116–1156, today KEGG + deepest-TCDB) **widens to include the
direct GO route**: it is a routing flag into gbm / mbg, and those tools now return GO rows by
default, so a gene with only GO rows must route there. Existing `gene_overview` goldens move for
GO-only genes; intended. Any per-row routing hint derived from `evidence_sources` follows the same
rule. No separate `has_go_transport` counter.

### 3.5 `list_metabolites`

- `evidence_sources` filter accepts `go_transport` (`_VALID_EVIDENCE_SOURCES`, MCP `Literal` at
  tools.py ~8180, field descriptions at ~552 / ~646 widen from three values to four).
- Rows surface `go_transport_organism_names` / `go_transport_organism_count` (sparse; absent = no
  directly annotated gene path, **not** "no GO transport edge" — say so in the field description).
- **Organism filter = union (decided):** `organism_names` matches a metabolite if the organism is
  in `organism_names` **or** `go_transport_organism_names`. `top_organisms` counts the same union.
  A GO-only metabolite (`organism_count = 0`) now appears under its organisms. Rows keep both lists
  separately so the route is still readable per row.
- `by_evidence_source` already rolls up `go_transport` (absorbed).

### 3.6 `kg_release_info`

Pass `Schema_info.go_transport_excluded_targets` through (`_KG_IDENTITY_FIELDS` + response model).
The gbm/mbg warning (§3.1) reads it from the same cached source.

### 3.7 `kg_schema` — edge-type descriptions (new feature)

`kg_schema` has labels and properties but no relationship-type descriptions today. Add a
hand-authored block next to `config/schema_baseline.yaml` (builder picks file name / shape, e.g.
`config/edge_descriptions.yaml`, keyed by relationship type) and surface a `description` per
relationship type in `kg_schema` output where one exists. Seed it with the KG's four ready-to-copy
caveat paragraphs (`go-transport-substrates.md` § "Caveat text") for the four GO edges. Other edge
types: none required now.

### 3.8 Docs

- `docs://analysis/transport` — new hand-authored recipe (TPS-005): the routes (KEGG metabolism,
  TCDB transport, GO transport), each route's bias, how to read agreement (routes are correlated —
  InterPro2GO vs eggNOG share homology), what an empty answer means (incl. the filter list), MF vs
  BP, direct vs inherited, class reach (GO is_a walk vs `Metabolite_in_metabolite_class`), the
  Cypher examples from the KG doc. Short; link from `docs://analysis/metabolites` and the guide.
  If it slips, the tool YAMLs carry the caveats and the release still ships.
- Tool YAMLs (gbm, mbg, gene_overview, list_metabolites, kg_release_info, kg_schema,
  list_filter_values): new examples with real rows (urea MED4 urtA; siderophore AltDE role row;
  an inherited example with `go_include_ancestors=True`), mistakes ("a GO row is a term
  definition"; "BP ≠ transporter — MED4 ftn reaches iron via iron ion transport"; "empty for H⁺/Na⁺
  is curation"), chaining.
- `docs://analysis/metabolites`: the "three pipelines" prose → four evidence values; the fourth-value
  paragraph (added at absorb) updates to "surfaced in gbm/mbg".
- CLAUDE.md tool table rows for gbm, mbg, list_metabolites, gene_overview, kg_release_info,
  kg_schema (700-char row limit).
- `kg_claims.yaml`: add claims for any KG number the new prose quotes (MED4 59 genes, role counts).

## 4. Constraints

- Read-only; no KG changes needed. No new KG precompute is required by any decided item
  (inherited rows are opt-in, so direct-only KG rollups stay consistent with defaults).
- Layer rules (`layer-rules` skill), Mode B of `add-or-update-tool` (≥2 tools).
- GO rows by default changes existing gbm/mbg outputs: goldens, example responses and pinned
  integration counts for those tools will move. That is intended; regenerate them in the build and
  record the move in the CHANGELOG `### Changed` (not an absorb).
- Corner-case scenarios: GO arm with an organism that has no GO-route genes; role id with no
  edges; excluded target id with no node; `go_include_ancestors=True` on a gene with no ancestors.
- Release: explorer MCP release; the KG release then sets `mcp_min_version` to it (coordinate via
  the asks doc).
- **No backward compatibility with KGs lacking slice 1** (decided): the explorer may assume the four
  GO edges, `Schema_info.go_transport_excluded_targets` and the `go_transport` value exist. No
  degrade paths. Add the four GO edge types and `Tcdb_family_transports_chemical_role` to
  `config/schema_baseline.yaml` as required.

## 5. Decided by the user (2026-10-20)

1. GO rows appear by default.
2. Row grain: per gene × GO term × target (long).
3. GO ancestor inheritance: opt-in flag, rows marked (option B).
4. `list_metabolites` organism filter and `top_organisms`: union with `go_transport_organism_names`.
5. Role inputs reach TCDB role edges too.
6. Possible additions → backlog, unless small or needing a KG precompute.
7. TCDB best hit out of scope.
8. No backward compatibility with a KG that lacks slice 1; assume the dev graph.

## 6. Calls made by the designer (check these)

- Field names: `go_term_id`, `go_term_name`, `go_namespace` (full names), `go_evidence`,
  `go_sources`, `go_term_depth`, `go_axiom_term_id/_name`, `target_kind`; `go_chebi_ids` verbose.
- Parameter name `go_include_ancestors`.
- Role targets ride in `metabolite_id` + `target_kind`, not separate `role_id` fields.
- GO rows sort after all metabolism and TCDB rows.
- `transport_substrate_resolution` null on GO rows.
- Inherited rows: emitted only for (gene, target) pairs with no direct GO path; one row per
  (gene, own term, target) at minimum depth; TCDB/KEGG not consulted.
- mbg returns TCDB role rows too, so mbg TCDB rollups move for genes with TCDB role edges.
- `has_chemistry` widens to the direct GO route (routing flag); no `has_go_transport`.
- Role-id input handling via a per-call switch on the shared canonicaliser (gbm / mbg only);
  neurotransmitter warning in gbm (input) and mbg (returned row); excluded-target warning gbm only.

## 7. Left to the builder

Builder function split (one new arm builder per tool vs. parameterised), summary-query shape,
exact edge-descriptions file format, YAML example selection, test layout, verifying the
`stereo_relatives` invariant under the widened `by_metabolite`.
