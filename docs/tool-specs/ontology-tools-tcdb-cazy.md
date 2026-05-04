# Tool spec: surface TCDB and CAZy in ontology tools (Mode B cross-tool)

## Purpose

Add TCDB (`TcdbFamily`) and CAZy (`CazyFamily`) as first-class ontologies
in the existing ontology surface so users can browse, search, and pull
gene-set memberships through the same tool family they already use for
GO, EC, KEGG, COG, CyanoRak, TIGR, Pfam, and BRITE.

KG side already landed (commit 2026-05-02; see
[docs/kg-changes/tcdb-cazy-ontologies.md](https://github.com/osnatw/multiomics_biocypher_kg/blob/main/docs/kg-changes/tcdb-cazy-ontologies.md)).
Both node types follow the standard ontology shape (`id`, `level: int`,
`level_kind: str`, `name`, `gene_count`, `organism_count`), have
fulltext indexes, and use the canonical `_is_a_` parent relationship —
no KG schema work is required.

This is a **Mode B cross-tool small change**: the four ontology tools
all dispatch on `ONTOLOGY_CONFIG` plus the central `_hierarchy_walk`
helper, so the explorer-side change is essentially "extend the config
table by two rows + bump the closed `Literal` enums on the tool
wrappers."

## Out of Scope

- **No new tools.** Only extending existing ontology tools to recognize
  two more dimensions.
- **No new filters.** TCDB has a `tc_class_id` per-node pointer (analog
  of BRITE's `tree`) that could power a class-level scope filter. Defer
  until a user demand surfaces — surface tcdb as a plain hierarchical
  ontology first.
- **No `genes_by_metabolite` changes.** Substrate edges are already
  surfaced by the chemistry-slice-1 tool family.
- **No new `Gene.tcdb_family_count` / `Gene.cazy_family_count` rollup
  surfacing in `gene_overview` or `list_organisms`.** Those are
  routing-signal extensions and belong to a separate scope-creep-prone
  follow-up — file as a backlog item (see "Out of scope notes" below).

## Status / Prerequisites

- [x] KG schema landed 2026-05-02
- [x] Live KG verified — node counts, edge counts, fulltext indexes,
      level distributions all match the KG-side spec.
- [ ] Scope reviewed with user (this spec)
- [ ] Result-size controls (no change — every affected tool keeps its
      current envelope)
- [ ] Ready for Phase 2 (build)

## Use cases

- **search_ontology(ontology="tcdb", search_text="sucrose")** — find
  TCDB families that move sucrose. Returns `tcdb:*` IDs for use with
  `genes_by_ontology(ontology="tcdb", term_ids=[...])`.
- **search_ontology(ontology="cazy", search_text="GH13")** — find
  glycoside hydrolase family GH13.
- **ontology_landscape(organism="MED4")** — TCDB and CAZy now
  appear alongside the existing 10 ontologies in the multi-ontology
  fan-out, with per-level enrichment-eligibility breakdowns.
- **genes_by_ontology(ontology="tcdb", term_ids=["tcdb:1.A.1"], organism="MED4")**
  — drill from a TCDB family to its member genes (with descendant
  walk; e.g. `tcdb:1.A.1` expands to all 31 voltage-gated-ion-channel
  subfamilies).
- **gene_ontology_terms(locus_tags=[...], ontology="cazy", mode="rollup", level=0)**
  — what CAZy class (GH/GT/PL/CE/AA/CBM) does each gene belong to.
- Already-existing chains continue to work via `genes_by_metabolite`
  for the substrate-anchored side of TCDB.

## Tool chains

```
search_ontology(ontology="tcdb")                # find term IDs
  → genes_by_ontology(ontology="tcdb", term_ids=[...])
  → differential_expression_by_gene(locus_tags=[...])

ontology_landscape(organism="MED4")             # rank by relevance
  → search_ontology(ontology="tcdb", level=2)   # browse families
  → genes_by_ontology(...)

genes_by_metabolite(metabolite_ids=[...])       # already-existing chain
  → top_tcdb_families                           # rolled-up
  → genes_by_ontology(ontology="tcdb", term_ids=[...])    # NEW path
```

## KG dependencies

| Node | Properties used |
|---|---|
| `TcdbFamily` | `id`, `name`, `tcdb_id`, `level: int`, `level_kind`, `gene_count`, `organism_count`, `metabolite_count`, `superfamily` (sparse), `tc_class_id` |
| `CazyFamily` | `id`, `name`, `cazy_id`, `level: int`, `level_kind`, `gene_count`, `organism_count` |

| Edge | Used for |
|---|---|
| `Gene_has_tcdb_family` | gene→leaf bind in `_hierarchy_walk` |
| `Tcdb_family_is_a_tcdb_family` | hierarchy walk up/down |
| `Gene_has_cazy_family` | gene→leaf bind |
| `Cazy_family_is_a_cazy_family` | hierarchy walk up/down |

| Fulltext index | Searched fields |
|---|---|
| `tcdbFamilyFullText` | `name`, `tcdb_id`, `superfamily` |
| `cazyFamilyFullText` | `name`, `cazy_id` |

**Live KG verified 2026-05-03:** 4844 TcdbFamily / 64 CazyFamily nodes;
10568 Gene_has_tcdb_family / 1180 Gene_has_cazy_family edges; 4838 +
58 hierarchy edges; both fulltext indexes present with the expected
properties.

---

## Affected files (Mode B per-file briefing)

This is a **5-tool surface refresh**, not a new tool, so the layer-cut
agents each get a punch-list rather than one new builder per agent.

| Layer | File | Edits |
|---|---|---|
| Constants | `multiomics_explorer/kg/constants.py` | Append `"tcdb"`, `"cazy"` to `ALL_ONTOLOGIES` (preserve current ordering — append at end so existing 10 ontologies keep their slot for regression-fixture determinism) |
| Query builder | `multiomics_explorer/kg/queries_lib.py` | Add 2 entries to `ONTOLOGY_CONFIG` |
| API | `multiomics_explorer/api/functions.py` | None expected — fan-out reads `ALL_ONTOLOGIES` already; verify no place hard-codes the 10-ontology list. |
| MCP wrapper | `multiomics_explorer/mcp_server/tools.py` | Bump 5 `Literal[...]` enums + 1 description on `search_ontology` |
| Inputs | `multiomics_explorer/inputs/tools/{search_ontology,ontology_landscape,genes_by_ontology,gene_ontology_terms}.yaml` | Add `tcdb` / `cazy` to enum lists in examples + add 1–2 examples per yaml |
| Skill table | `CLAUDE.md` | Update `search_ontology` and `genes_by_ontology` descriptions to include TCDB and CAZy |
| Generated about | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md` | Regenerated by `scripts/build_about_content.py` — never hand-edited |

### Code change: `ONTOLOGY_CONFIG`

Append in `kg/queries_lib.py`:

```python
"tcdb": {
    "label": "TcdbFamily",
    "gene_rel": "Gene_has_tcdb_family",
    "hierarchy_rels": ["Tcdb_family_is_a_tcdb_family"],
    "fulltext_index": "tcdbFamilyFullText",
},
"cazy": {
    "label": "CazyFamily",
    "gene_rel": "Gene_has_cazy_family",
    "hierarchy_rels": ["Cazy_family_is_a_cazy_family"],
    "fulltext_index": "cazyFamilyFullText",
},
```

Both fall through `_hierarchy_walk`'s "single-label tree ontologies"
branch (the same one GO BP/MF/CC, EC, KEGG, CyanoRak, TIGR, COG follow)
— no helper changes.

### Code change: `ALL_ONTOLOGIES`

`kg/constants.py`:

```python
ALL_ONTOLOGIES: list[str] = [
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam",
    "brite", "tcdb", "cazy",
]
```

### Code change: 5 `Literal` enums on tool wrappers

In `mcp_server/tools.py`, append `"tcdb", "cazy"` to:

| Tool | Line | Notes |
|---|---|---|
| `genes_by_ontology` | 1810 | Required Literal |
| `gene_ontology_terms` | 1953 | `Literal[...] \| None` (None means "all ontologies") |
| `ontology_landscape` | 5053 | `Literal[...] \| None` |
| `pathway_enrichment` | 5128 | shares same Literal — keep consistent |
| `cluster_enrichment` | 5246 | shares same Literal — keep consistent |

Plus `search_ontology` (line 1685) — open `str` already, just update
the description string to mention `'tcdb'` and `'cazy'`.

> **Scope question for user**: extending the Literal on
> `pathway_enrichment` / `cluster_enrichment` lets users run ORA against
> TCDB / CAZy gene sets. The underlying machinery already dispatches on
> `ONTOLOGY_CONFIG`, so there's no extra Cypher work. Default
> recommendation: **include both**. They're the same closed Literal
> shape and the cost of leaving them out is "user passes `tcdb`,
> wrapper rejects with a confusing error and stale enum." Flag if you
> want to defer them.

---

## Verified Cypher

### `search_ontology` — TCDB

(Standard fulltext-index pattern via `_hierarchy_walk` config; query
shape is identical to the existing 10 ontologies.)

```cypher
CALL db.index.fulltext.queryNodes('tcdbFamilyFullText', $search_text)
YIELD node AS t, score
RETURN t.id AS id, t.name AS name, score,
       t.level AS level, t.tree AS tree, t.tree_code AS tree_code
ORDER BY score DESC, id
LIMIT $limit
```

`t.tree` and `t.tree_code` are NULL for TcdbFamily nodes (BRITE-only
properties). The existing wrapper already returns NULL cleanly in those
columns for non-BRITE ontologies (e.g. EcNumber, KeggTerm).

### `search_ontology` — CAZy

Same pattern with `cazyFamilyFullText`.

### `genes_by_ontology` — TCDB, term_ids mode (walk DOWN)

```cypher
MATCH (t:TcdbFamily) WHERE t.id IN $term_ids
MATCH (t)<-[:Tcdb_family_is_a_tcdb_family*0..]-(leaf:TcdbFamily)
MATCH (g:Gene {organism_name: $org})-[:Gene_has_tcdb_family]->(leaf)
WITH t, count(DISTINCT g) AS n_g_per_term, ...
```

**Verified live KG 2026-05-03:** `tcdb:1.A.1` (Voltage-gated Ion
Channel Superfamily) → 31 descendants → 1 gene in MED4. Path resolves
correctly.

### `genes_by_ontology` — CAZy, level mode (walk UP)

```cypher
MATCH (g:Gene {organism_name: $org})-[:Gene_has_cazy_family]->(leaf:CazyFamily)
MATCH (leaf)-[:Cazy_family_is_a_cazy_family*0..]->(t:CazyFamily)
WHERE t.level = $level
WITH t, count(DISTINCT g) AS n_g_per_term, ...
```

**Verified live KG 2026-05-03:** at `level=0` for MED4 returns
`cazy:GT` (17 genes), `cazy:GH` (6 genes), `cazy:CBM` (2 genes). Counts
plausible.

### `ontology_landscape` — TCDB, MED4

**Verified live KG 2026-05-03:**

| level | level_kind | n_terms_with_genes (5..500 filter) | min_g | max_g |
|---|---|---|---|---|
| 0 | tc_class | 3 | 8 | 67 |
| 1 | tc_subclass | 3 | 7 | 63 |
| 2 | tc_family | 2 | 8 | 52 |
| 3 | tc_subfamily | 6 | 5 | 7 |
| 4 | tc_specificity | 2 | 5 | 5 |

### `ontology_landscape` — CAZy, MED4

**Verified live KG 2026-05-03:**

| level | level_kind | n_terms_with_genes (5..500 filter) | min_g | max_g |
|---|---|---|---|---|
| 0 | cazy_class | 2 | 6 | 17 |
| 1 | cazy_family | 1 | 6 | 6 |

CAZy is a small ontology (64 nodes, 6 classes / 58 families) — only a
handful of terms ever pass the default `min_gene_set_size=5` filter.
This is expected, not a bug. Document in the yaml so users don't think
the tool dropped data.

### `gene_ontology_terms` — TCDB leaf mode

```cypher
MATCH (g:Gene {organism_name: $org})-[:Gene_has_tcdb_family]->(t:TcdbFamily)
WHERE g.locus_tag IN $locus_tags
RETURN g.locus_tag, t.id, t.name, t.level
```

### `gene_ontology_terms` — CAZy rollup mode at level=0

**Verified live KG 2026-05-03:** rolling up CAZy memberships of MED4
genes to level=0 yields `cazy:GT` / `cazy:GH` / `cazy:CBM` per gene as
expected. Some genes belong to multiple top-level classes (e.g.
PMM0584 → both CBM and GH; PMM1322 → both CBM and GH) — multi-class
membership is normal and correctly de-duped per `(g, t)`.

---

## Special handling

- **Multi-query orchestration:** `ontology_landscape` already loops over
  `ALL_ONTOLOGIES` when no specific ontology is given (api/functions.py
  line 4116). Adding TCDB and CAZy to the list extends the loop by two
  iterations. No new orchestration logic.
- **Lucene retry / fulltext escape:** unchanged — fulltext path is
  identical to other ontologies and is index-name-driven via
  `cfg["fulltext_index"]`.
- **Level / `level_kind` semantics:** same convention as other
  ontologies. `level: 0 = root` (broadest); `level_kind` is the
  human-readable label per level (`tc_class`...`tc_specificity`,
  `cazy_class`...`cazy_subfamily`).

---

## Test surface

Mode B small change — tests are mostly **regenerations + extensions**
of existing ontology tests, not net-new test classes.

| Layer | Test changes |
|---|---|
| `tests/unit/test_query_builders.py` | Extend the existing parametrized ontology tests (over `ALL_ONTOLOGIES`) so tcdb / cazy land naturally in every per-ontology assertion. Add 2 new parametrize ids (`tcdb`, `cazy`) only where assertions hard-code expected labels (e.g. `_hierarchy_walk` label-match tests). |
| `tests/unit/test_api_functions.py` | If any test mocks `ALL_ONTOLOGIES` or asserts the count "10 ontologies", bump to 12. |
| `tests/unit/test_tool_wrappers.py` | Update `Literal`-validating tests for the 5 wrappers; ensure `tcdb` and `cazy` accepted, no-op tcdb param doesn't break envelope shape. |
| `tests/integration/test_mcp_tools.py` | Add 1 smoke test per ontology tool with `ontology="tcdb"` and 1 with `ontology="cazy"` against live KG (returns rows, no errors). |
| `tests/regression/test_regression.py` | `TOOL_BUILDERS` is keyed by tool, not by ontology — no change. Regression fixtures for the 4 ontology tools that depend on `ALL_ONTOLOGIES` ordering need regen with `--force-regen` per `feedback_kg_rebuild_regen_fixtures` workflow. |

**Anti-scope-creep guardrail (mandatory in implementer briefs):** ADD
only — do not modify, rename, or rebaseline pre-existing ontology
tests. If `--force-regen` reveals a regression that's NOT explained by
the addition of tcdb/cazy, REPORT AS A CONCERN; do not silently retune.
The 10 existing ontologies' fixtures must change only by appending new
rows for tcdb/cazy, not by editing existing rows.

---

## About-content updates (yaml)

Each of the 4 ontology-tool yamls gets:

1. **Description bump** (where the yaml lists the supported ontologies)
   to mention TCDB and CAZy.
2. **At least one new example** demonstrating the new dimension. Suggested:
   - `search_ontology.yaml`: "Find TCDB families that move sucrose"
     (`ontology="tcdb"`, `search_text="sucrose"`).
   - `ontology_landscape.yaml`: include sample row showing `cazy` and
     `tcdb` in the `by_ontology` envelope.
   - `genes_by_ontology.yaml`: "TCDB family → gene drill-down"
     (`ontology="tcdb"`, `term_ids=["tcdb:1.A.1"]`, `organism="MED4"`).
   - `gene_ontology_terms.yaml`: "CAZy class membership rollup"
     (`mode="rollup"`, `level=0`, `ontology="cazy"`).
3. **Mistakes / chaining** entries — add a bullet on
   "TCDB substrate questions chain via `genes_by_metabolite`, not
   `genes_by_ontology`. Use ontology tools for *family-level* questions."

Run `uv run python scripts/build_about_content.py` after yaml edits to
regenerate the skills tree (per `feedback_skill_content_yaml_workflow`).

---

## Out-of-scope notes (file as backlog)

These could ride along but explicitly do NOT in this spec:

- **`gene_overview` exposing `tcdb_family_count` / `cazy_family_count`.**
  These are routing-signal counts already populated on Gene nodes per
  the KG-side spec. Surfacing them lets users route from `gene_overview`
  → `gene_ontology_terms(ontology="tcdb")`. Per
  `project_dm_slice2_shipped` precedent, that's a "discovery surface
  DM-awareness" pass that touches multiple discovery tools — too
  scope-prone to bundle here.
- **`list_organisms` exposing TCDB / CAZy capability rollups.** Same
  reasoning.
- **`tc_class` filter on TCDB ontology tools** (analog of BRITE `tree`).
  Defer until user demand.
- **`ontology="tcdb"` enrichment chain validation.** `pathway_enrichment`
  and `cluster_enrichment` will *accept* tcdb after the Literal bump,
  but the gene-set sizes are tiny (most TCDB families have <5 MED4
  genes) — ORA may produce nothing significant. Acceptable for the
  surface refresh; Phase 2 should add a smoke test that confirms the
  call returns a well-formed envelope (even if empty), not that it
  yields biologically meaningful enrichment.

---

## Implementation order (Phase 2)

1. **RED stage** — `test-updater` writes failing tests against
   `ALL_ONTOLOGIES = [..., "tcdb", "cazy"]` and the bumped Literals.
2. **GREEN stage** — 4 implementer agents in parallel:
   - `query-builder`: add the 2 entries to `ONTOLOGY_CONFIG` in
     `kg/queries_lib.py`.
   - `api-updater`: verify `api/functions.py` requires no change
     beyond reading the bumped `ALL_ONTOLOGIES` list (likely 0 LoC);
     touch `__init__.py` only if exports changed (they shouldn't).
   - `tool-wrapper`: bump the 5 `Literal`s + the `search_ontology`
     description in `mcp_server/tools.py`.
   - `doc-updater`: append to `kg/constants.py` (new ontology entries),
     edit the 4 yamls, regen via `build_about_content.py`, update
     `CLAUDE.md` rows for `search_ontology` and `genes_by_ontology`.
3. **VERIFY stage** — code-review hard gate (live-Cypher correctness:
   confirm node label spellings `TcdbFamily` / `CazyFamily`, edge type
   spellings, fulltext index names — these are the silent-failure mode
   per the `list_metabolites` smoke-test lesson). Then unit + integration
   + regression (with `--force-regen` for the 4 ontology tools'
   landscape fixtures, then verified clean).

→ **Gate:** user approves this frozen spec. After approval, no
field/parameter additions without re-spec.
