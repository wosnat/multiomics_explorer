# Tool spec: surface PSORTb + SignalP in ontology tools (Mode B cross-tool)

## Purpose

Add PSORTb subcellular-localization (`SubcellularLocalization`) and SignalP
signal-peptide-type (`SignalPeptideType`) as first-class ontologies in the
existing ontology surface so users can browse, search, and pull gene-set
memberships through the same tool family they already use for GO, EC, KEGG,
COG, CyanoRak, TIGR, Pfam, BRITE, TCDB, and CAZy.

KG side already landed:
- PSORTb: commit 2026-05-26 (see [docs/kg-changes/psortb-extension.md](https://github.com/wosnat/multiomics_biocypher_kg/blob/main/docs/kg-changes/psortb-extension.md))
- SignalP: commit 2026-05-27 (see [docs/kg-changes/signalp-extension.md](https://github.com/wosnat/multiomics_biocypher_kg/blob/main/docs/kg-changes/signalp-extension.md))

Both follow the standard ontology shape with two specific wrinkles versus the
existing 12 ontologies:

1. **Flat, 5 nodes each** — like `cog_category` / `tigr_role`. Single `level: 0`,
   no `level_kind`, no `*_is_a_*` hierarchy edges. They fall through
   `_hierarchy_walk`'s existing "flat ontologies" branch.
2. **Scored edges** — KG's first two scored ontology edges. `Gene_has_subcellular_localization`
   carries `score: float` (PSORTb confidence ∈[7.5, 10.0]).
   `Gene_has_signal_peptide_type` carries `probability: float` (∈[0, 1]),
   plus `cleavage_site: int` and `cleavage_probability: float` (both absent
   when SignalP reports no cleavage site).
3. **1:1 mapping** — at most one localization / signal-peptide-type edge per
   gene. Routing strings `Gene.subcellular_localization` and
   `Gene.signal_peptide_type` are already on the Gene node (post-import
   denormalization).

This is a **Mode B cross-tool small change** modeled on the
[TCDB/CAZy spec](ontology-tools-tcdb-cazy.md): the four ontology tools
all dispatch on `ONTOLOGY_CONFIG` + `_hierarchy_walk`, so the bulk of the
explorer-side change is "extend the config table by two rows + bump the
closed `Literal` enums on the tool wrappers."

The novel work is **edge-property surfacing**: existing ontology builders
use unbound relationships (`MATCH (g)-[:Gene_has_pfam]->`), so surfacing
`score` / `probability` requires binding the rel (`MATCH (g)-[r:...]->`)
and threading per-row columns through two row-bearing detail builders.

## Out of Scope

- **No new tools.** Only extending existing ontology tools to recognize two
  more dimensions plus the edge-property columns.
- **No edge-score filter params.** `min_score` / `min_probability` filters on
  `genes_by_ontology` are routing-signal extensions; defer to a follow-up
  spec when a user actually asks. Today users can post-filter rows or use
  `run_cypher`.
- **No folding into `Gene.annotation_types` / `informative_annotation_types` /
  `annotation_quality`.** KG-side docs are explicit: PSORTb / SignalP are
  **structural** (where the gene is / how its product is handled), not
  **functional** (what it does). Folding would inflate functional-annotation
  coverage and skew `genes_by_function` `min_quality`.
- **No `gene_overview` / `list_organisms` rollups for `subcellular_localization` /
  `signal_peptide_type`.** Routing strings already on the Gene node surface
  via `gene_details` for free; broader discovery-surface awareness is a
  scope-creep-prone follow-up (per the `project_dm_slice2_shipped` precedent).
  File as backlog.
- **No full SignalP probability vector.** Per KG-side decision, only the
  winning-class probability is stored on the edge; the 6-class likelihood
  vector is intentionally absent.

## Status / Prerequisites

- [x] PSORTb KG schema landed 2026-05-26 (79,361 edges, 5 nodes)
- [x] SignalP KG schema landed 2026-05-27 (13,613 edges, 5 nodes)
- [x] Live KG verified — node counts, edge counts, fulltext indexes,
      level=0 distributions all match the KG-side specs
- [x] `Gene.subcellular_localization` / `Gene.signal_peptide_type` routing
      strings populated on Gene nodes (per memory `project_seq_neighbors_shipped`
      and the KG-side strand-fix rebuild)
- [ ] Scope reviewed with user (this spec)
- [ ] Result-size controls (no change — every affected tool keeps its
      current envelope)
- [ ] Ready for Phase 2 (build)

## Use cases

- **`search_ontology(ontology="subcellular_localization", search_text="outer")`** —
  find the OuterMembrane localization (returns `psortb_OuterMembrane`).
- **`search_ontology(ontology="signal_peptide_type", search_text="lipo")`** —
  find lipoprotein-related signal peptide types (`signalp_LIPO`, `signalp_TATLIPO`).
- **`ontology_landscape(organism="MED4")`** — both new ontologies appear
  alongside the existing 12 in the multi-ontology fan-out. Each contributes
  one `level=0` row per organism with the 5 (or fewer, for small organisms)
  observed terms.
- **`genes_by_ontology(ontology="subcellular_localization", term_ids=["psortb_OuterMembrane"], organism="MED4")`** —
  pull all outer-membrane proteins in MED4, with `localization_score` per
  gene available for ranking client-side.
- **`gene_ontology_terms(locus_tags=[...], ontology="signal_peptide_type", mode="leaf", organism="MED4")`** —
  for each input gene, return its single SignalP type call with
  `signal_peptide_probability` and `signal_peptide_cleavage_site`.
- **`pathway_enrichment(experiment_ids=[...], ontology="subcellular_localization", direction="up", organism="MED4")`** —
  "Are up-regulated genes enriched for outer-membrane proteins relative to
  background?" Small N (5 categories) but a real biological question.

## Tool chains

```
search_ontology(ontology="subcellular_localization")     # find term IDs
  → genes_by_ontology(ontology="subcellular_localization",
                       term_ids=["psortb_OuterMembrane"], organism="MED4")
  → differential_expression_by_gene(locus_tags=[...])

ontology_landscape(organism="MED4")                      # rank by relevance
  → genes_by_ontology(ontology="signal_peptide_type",
                       term_ids=["signalp_LIPO"], organism="MED4")

gene_overview(locus_tags=[...])                          # routing
  → gene_ontology_terms(ontology="subcellular_localization",
                          locus_tags=[...], organism="MED4")
  → reads localization_score for ranking

pathway_enrichment(experiment_ids=[...],                 # secretome shift?
                    ontology="signal_peptide_type",
                    direction="up", organism="MED4")
```

## KG dependencies

| Node | Properties used |
|---|---|
| `SubcellularLocalization` | `id` (`psortb_*`), `name`, `psortb_id`, `level: int` (always 0), `gene_count`, `organism_count` |
| `SignalPeptideType` | `id` (`signalp_*`), `name`, `signalp_id`, `level: int` (always 0), `gene_count`, `organism_count` |

| Edge | Properties | Used for |
|---|---|---|
| `Gene_has_subcellular_localization` | `score: float`, `rank_by_score: int` | gene→leaf bind; `score` surfaced read-only on rows |
| `Gene_has_signal_peptide_type` | `probability: float`, `cleavage_site: int?`, `cleavage_probability: float?`, `rank_by_probability: int` | gene→leaf bind; `probability` + cleavage info surfaced read-only on rows |

| Fulltext index | Searched fields |
|---|---|
| `subcellularLocalizationFullText` | `name`, `psortb_id` |
| `signalPeptideTypeFullText` | `name`, `signalp_id` |

Note: no `*_is_a_*` hierarchy edges (flat ontology). No `level_kind` property
(only one level). The existing ontology query builders already handle missing
`level_kind` via `IS NOT NULL` coalesces — verified at
[multiomics_explorer/kg/queries_lib.py:2434](multiomics_explorer/kg/queries_lib.py#L2434).

**Live KG observed counts (2026-05-27):**
- PSORTb: SubcellularLocalization 5 (Cytoplasmic 49,251 · CytoplasmicMembrane
  25,118 · OuterMembrane 2,049 · Periplasmic 1,871 · Extracellular 1,072),
  `Gene_has_subcellular_localization` 79,361 edges.
- SignalP: SignalPeptideType 5 (SP 9,710 · LIPO 3,065 · TAT 441 · PILIN 314 ·
  TATLIPO 83), `Gene_has_signal_peptide_type` 13,613 edges.

---

## Affected files (Mode B per-file briefing)

This is a **5-tool surface refresh** plus edge-prop plumbing on two of those
tools. Not a new tool, but the edge-prop work is the meaningful change.

| Layer | File | Edits |
|---|---|---|
| Constants | [multiomics_explorer/kg/constants.py](multiomics_explorer/kg/constants.py) | Append `"subcellular_localization"`, `"signal_peptide_type"` to `ALL_ONTOLOGIES` (preserve current ordering — append at end so existing 12 ontologies keep their slot for regression-fixture determinism) |
| Query builder | [multiomics_explorer/kg/queries_lib.py](multiomics_explorer/kg/queries_lib.py) | Add 2 entries to `ONTOLOGY_CONFIG` with new `edge_props` field. Modify `build_genes_by_ontology_detail` and `build_gene_ontology_terms_*` builders to bind the gene→leaf relationship and emit per-config edge-prop columns (null on ontologies without `edge_props`). |
| API | [multiomics_explorer/api/functions.py](multiomics_explorer/api/functions.py) | None expected — fan-out reads `ALL_ONTOLOGIES`. Verify no place hard-codes the 12-ontology list. Pass through new row columns (Pydantic row classes may need optional fields). |
| MCP wrapper | [multiomics_explorer/mcp_server/tools.py](multiomics_explorer/mcp_server/tools.py) | Bump 5 `Literal[...]` enums (lines 2265, 2430, 5534, 5629, 5774). Update `search_ontology` description (line 2125-2128). Add optional row fields for new edge-prop columns to relevant row Pydantic models. |
| Inputs | `multiomics_explorer/inputs/tools/{search_ontology,ontology_landscape,genes_by_ontology,gene_ontology_terms}.yaml` | Add `subcellular_localization` / `signal_peptide_type` to enum lists; add 1–2 examples per yaml |
| Skill table | [CLAUDE.md](CLAUDE.md) | Update `search_ontology` and `genes_by_ontology` descriptions to include the two new dimensions |
| Generated about | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md` | Regenerated by `scripts/build_about_content.py` — never hand-edited |

### Code change: `ONTOLOGY_CONFIG`

Append in `kg/queries_lib.py` after `cazy`:

```python
"subcellular_localization": {
    "label": "SubcellularLocalization",
    "gene_rel": "Gene_has_subcellular_localization",
    "hierarchy_rels": [],
    "fulltext_index": "subcellularLocalizationFullText",
    "edge_props": [("score", "localization_score")],
},
"signal_peptide_type": {
    "label": "SignalPeptideType",
    "gene_rel": "Gene_has_signal_peptide_type",
    "hierarchy_rels": [],
    "fulltext_index": "signalPeptideTypeFullText",
    "edge_props": [
        ("probability", "signal_peptide_probability"),
        ("cleavage_site", "signal_peptide_cleavage_site"),
        ("cleavage_probability", "signal_peptide_cleavage_probability"),
    ],
},
```

The new optional `edge_props: list[tuple[str, str]]` field is a list of
`(neo4j_edge_property, output_column_name)` pairs. Absent / empty for the
existing 12 ontologies, which means the row-builders emit a single `null AS
localization_score, null AS signal_peptide_probability, null AS
signal_peptide_cleavage_site, null AS signal_peptide_cleavage_probability`
block (same as the existing BRITE-only `tree` / `tree_code` null-emission
pattern on non-BRITE rows). The full set of columns is taken from the union
of all `edge_props` across `ONTOLOGY_CONFIG` so every row has the same shape.

Both fall through `_hierarchy_walk`'s "flat ontologies (no hierarchy_rels)"
branch (the same one `cog_category` and `tigr_role` follow) — no helper
changes for `_hierarchy_walk` itself.

### Code change: `ALL_ONTOLOGIES`

`kg/constants.py`:

```python
ALL_ONTOLOGIES: list[str] = [
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam",
    "brite", "tcdb", "cazy",
    "subcellular_localization", "signal_peptide_type",
]
```

### Code change: relationship binding in row builders

The two row-emitting builders need to bind the gene→leaf rel and project
edge properties. Today the detail builder reads
([queries_lib.py:2267-2269](multiomics_explorer/kg/queries_lib.py#L2267-L2269)):

```cypher
MATCH (g:Gene {organism_name: $org})-[:Gene_has_pfam]->(leaf:Pfam)
```

After: bind `r` so callers can project edge properties when `edge_props` is set:

```cypher
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_pfam]->(leaf:Pfam)
```

The change is purely additive (binding adds no row cost) and applies to all
ontologies, but the projection block only emits real columns for ontologies
that declare `edge_props`. For all other ontologies, the column emission is
`null AS localization_score, null AS signal_peptide_probability, ...`.

**Affected builder helpers:**

| Function | Why it changes |
|---|---|
| `_hierarchy_walk` | `bind_up` Cypher fragment gains `[r:gene_rel]` binding for all variants (single-label, flat, bridge, pfam). |
| `_genes_by_ontology_match_stage` | Walk-down branch (mode 1) also needs the rel binding — both `Gene_has_pfam` styles in the function need `[r:gene_rel]`. Bridge case for `brite` keeps `kegg` edge unbound — the brite edge has no per-row score. Carry `r` through `WITH t, collect(DISTINCT {g: g, r: r}) AS gene_rows` instead of `collect(DISTINCT g)`. |
| `build_genes_by_ontology_detail` | UNWIND collects `{g, r}` records. RETURN block appends `edge_props_columns` (derived once at build time from `ONTOLOGY_CONFIG`). |
| `build_gene_ontology_terms_detail` (both `leaf` and `rollup` paths) | Same rel-binding pattern. |
| `build_genes_by_ontology_per_term` / `_per_gene` | Aggregate builders — DO NOT need edge-prop columns (these return summary rollups, not row-level scores). Keep edge unbound to minimize diff. |

**Critical: `pathway_enrichment` / `cluster_enrichment`** use the same
`_genes_by_ontology_match_stage` helper through their TERM2GENE feed. The
helper's switch to `collect({g, r})` is backward-compatible as long as
downstream consumers project `gene.g` instead of `gene` directly. Verify in
the per-gene helper used by enrichment that this projection happens cleanly.

### Code change: 5 `Literal` enums on tool wrappers

In `mcp_server/tools.py`, append the new keys to (current line numbers from
the live tree):

| Tool | Line | Notes |
|---|---|---|
| `genes_by_ontology` | 2265 | Required Literal |
| `gene_ontology_terms` | 2430 | `Literal[...] \| None` (None means "all ontologies") |
| `ontology_landscape` | 5534 | `Literal[...] \| None` |
| `pathway_enrichment` | 5629 | shares same Literal — keep consistent |
| `cluster_enrichment` | 5774 | shares same Literal — keep consistent |

Plus `search_ontology` description string (lines 2125-2128) — the
`ontology` param is open `str`, just update the description to list the two
new dimensions.

### Code change: row Pydantic models

The two row-emitting tools have Pydantic row classes in `mcp_server/tools.py`:

- `GenesByOntologyResult` (line 2183) — row class for `genes_by_ontology`.
- `OntologyTermRow` (line 2374) — row class for `gene_ontology_terms`.

Both already follow the sparse-on-ontology-X pattern via `tree` / `tree_code`
fields (BRITE-only, null elsewhere). Add four optional fields to each, mirroring
that pattern:

```python
localization_score: float | None = Field(
    default=None,
    description="PSORTb confidence score (only set when "
                "ontology='subcellular_localization'). Range 7.5–10.0.",
)
signal_peptide_probability: float | None = Field(
    default=None,
    description="SignalP winning-class probability (only set when "
                "ontology='signal_peptide_type'). Range 0–1.",
)
signal_peptide_cleavage_site: int | None = Field(
    default=None,
    description="SignalP-predicted cleavage residue position (only set when "
                "ontology='signal_peptide_type'; absent when SignalP reports "
                "no cleavage site).",
)
signal_peptide_cleavage_probability: float | None = Field(
    default=None,
    description="SignalP cleavage-site probability (only set when "
                "ontology='signal_peptide_type' and cleavage_site present).",
)
```

---

## Verified Cypher

### `search_ontology` — subcellular_localization

```cypher
CALL db.index.fulltext.queryNodes('subcellularLocalizationFullText',
                                    $search_text)
YIELD node AS t, score
RETURN t.id AS id, t.name AS name, score,
       t.level AS level, t.tree AS tree, t.tree_code AS tree_code
ORDER BY score DESC, id
LIMIT $limit
```

`t.tree` / `t.tree_code` are NULL (BRITE-only properties). `t.level` is
always 0 (flat ontology).

### `search_ontology` — signal_peptide_type

Same pattern with `signalPeptideTypeFullText`.

### `genes_by_ontology` — subcellular_localization, term_ids mode (walk down — but flat, so no walk)

```cypher
UNWIND $term_ids AS input_tid
MATCH (t:SubcellularLocalization {id: input_tid})
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_subcellular_localization]->(t)
WITH t, collect(DISTINCT {g: g, r: r}) AS gene_rows
WHERE size(gene_rows) >= $min_gene_set_size
  AND ($max_gene_set_size IS NULL OR size(gene_rows) <= $max_gene_set_size)
UNWIND gene_rows AS row
WITH t, row.g AS g, row.r AS r
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.gene_category AS gene_category,
       t.id AS term_id, t.name AS term_name, t.level AS level,
       t.tree AS tree, t.tree_code AS tree_code,
       coalesce(t.is_uninformative, '') <> 'true' AS is_informative,
       r.score AS localization_score,
       null AS signal_peptide_probability,
       null AS signal_peptide_cleavage_site,
       null AS signal_peptide_cleavage_probability
ORDER BY t.id, g.locus_tag
```

**To verify against live KG (2026-05-27 rebuild):** for `psortb_OuterMembrane`
in MED4 the result should be ~2,049 / 45 ≈ 50 genes (rough average across the
45 organisms). Exact count to be captured at Phase 2 verification time.

### `genes_by_ontology` — signal_peptide_type, term_ids mode

```cypher
UNWIND $term_ids AS input_tid
MATCH (t:SignalPeptideType {id: input_tid})
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_signal_peptide_type]->(t)
WITH t, collect(DISTINCT {g: g, r: r}) AS gene_rows
WHERE size(gene_rows) >= $min_gene_set_size
  AND ($max_gene_set_size IS NULL OR size(gene_rows) <= $max_gene_set_size)
UNWIND gene_rows AS row
WITH t, row.g AS g, row.r AS r
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.gene_category AS gene_category,
       t.id AS term_id, t.name AS term_name, t.level AS level,
       t.tree AS tree, t.tree_code AS tree_code,
       coalesce(t.is_uninformative, '') <> 'true' AS is_informative,
       null AS localization_score,
       r.probability AS signal_peptide_probability,
       r.cleavage_site AS signal_peptide_cleavage_site,
       r.cleavage_probability AS signal_peptide_cleavage_probability
ORDER BY t.id, g.locus_tag
```

### `genes_by_ontology` — existing ontologies, e.g. `pfam`, after rel binding

```cypher
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_pfam]->(leaf:Pfam)
...
RETURN ...,
       null AS localization_score,
       null AS signal_peptide_probability,
       null AS signal_peptide_cleavage_site,
       null AS signal_peptide_cleavage_probability
```

`r` is bound but unused for these ontologies; the four edge-prop columns are
emitted as nulls. Row schema is identical across all ontologies.

### `ontology_landscape` — subcellular_localization

Level=0 only (flat), so the landscape returns exactly one row per organism
per ontology with `n_terms = 5` (or fewer for organisms with no Periplasmic /
Extracellular / OuterMembrane calls). Per-level enrichment-eligibility
breakdowns apply with the same default `min_gene_set_size=5` filter.

**Expected (to verify at Phase 2):**

| ontology | level | level_kind | n_terms_with_genes | min_g | max_g |
|---|---|---|---|---|---|
| subcellular_localization | 0 | null | 5 (MED4) | ~30 | ~1000 |
| signal_peptide_type | 0 | null | varies (likely 3-5 per organism) | small | small |

### `gene_ontology_terms` — subcellular_localization, leaf mode

```cypher
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_subcellular_localization]->(t:SubcellularLocalization)
WHERE g.locus_tag IN $locus_tags
RETURN g.locus_tag, t.id, t.name, t.level,
       r.score AS localization_score,
       null AS signal_peptide_probability,
       null AS signal_peptide_cleavage_site,
       null AS signal_peptide_cleavage_probability
```

Because the mapping is 1:1, each input gene with a confident call returns
exactly one row.

### `gene_ontology_terms` — signal_peptide_type, leaf mode, mixed cleavage status

For SignalP, `cleavage_site` / `cleavage_probability` are absent when
SignalP reports no cleavage site. Two rows:

| locus_tag | term_id | signal_peptide_probability | signal_peptide_cleavage_site | signal_peptide_cleavage_probability |
|---|---|---|---|---|
| PMM1234 | signalp_SP | 0.92 | 22 | 0.85 |
| PMM5678 | signalp_PILIN | 0.78 | null | null |

PILIN-type signal peptides typically have no cleavage site → cleavage_site
and cleavage_probability are null. SP type calls usually have cleavage info.

---

## Special handling

- **Multi-query orchestration:** `ontology_landscape` already loops over
  `ALL_ONTOLOGIES` when no specific ontology is given
  ([api/functions.py:1821](multiomics_explorer/api/functions.py#L1821)).
  Adding the two ontologies extends the loop by two iterations. No new
  orchestration logic.
- **Lucene retry / fulltext escape:** unchanged — fulltext path is identical
  and is index-name-driven via `cfg["fulltext_index"]`.
- **Level / `level_kind` semantics:** flat — `level: 0` only, `level_kind`
  absent. Existing builders use `IS NOT NULL` coalesces and return null
  cleanly for missing `level_kind`. Documented for users in the yaml.
- **Routing strings via gene_details:** `Gene.subcellular_localization` and
  `Gene.signal_peptide_type` are already exposed via `gene_details` (`g{.*}`).
  Users don't need a new tool to get the per-gene call; the new ontology
  surface adds the *score*, the *term-level rollup*, and the
  *cross-organism* dimensions.
- **No flag for "no confident call":** absence of an edge encodes "no
  confident call" (PSORTb `Unknown` and SignalP `OTHER` sentinels are
  skipped at KG-build time). So `genes_by_ontology` only ever returns genes
  with a confident call — same convention as every other ontology.

---

## Test surface

Mode B small change with a real query-builder diff (rel binding). Tests are
mostly **regenerations + extensions** of existing ontology tests, plus
targeted new tests for the edge-prop columns.

| Layer | Test changes |
|---|---|
| `tests/unit/test_query_builders.py` | Extend parametrized ontology tests (over `ALL_ONTOLOGIES`) so the two new keys land naturally in every per-ontology assertion. Add 2 new parametrize ids (`subcellular_localization`, `signal_peptide_type`) where assertions hard-code expected labels. **New tests** verifying: (a) rel-binding present in builder output for ontologies with `edge_props`, (b) edge-prop columns emitted as `r.<neo4j_prop>` for matching ontology, `null AS <output_column>` for non-matching ontologies, (c) row shape is constant across all 14 ontologies (same column set). |
| `tests/unit/test_api_functions.py` | If any test mocks `ALL_ONTOLOGIES` or asserts the count "12 ontologies", bump to 14. Row-schema tests for `genes_by_ontology` and `gene_ontology_terms` expect the 4 new optional columns. |
| `tests/unit/test_tool_wrappers.py` | Update `Literal`-validating tests for the 5 wrappers; ensure `subcellular_localization` and `signal_peptide_type` accepted, no-op edge-prop columns don't break envelope shape on other ontologies. Row Pydantic-model tests for the 4 new optional fields. |
| `tests/integration/test_mcp_tools.py` | Add 1 smoke test per ontology tool with `ontology="subcellular_localization"` and 1 with `ontology="signal_peptide_type"` against live KG. For `genes_by_ontology`: assert `localization_score` is non-null on PSORTb rows and null on every other ontology. For `gene_ontology_terms`: assert SignalP rows with cleavage_site populated AND rows without it both appear cleanly. |
| `tests/regression/test_regression.py` | `TOOL_BUILDERS` keyed by tool, not ontology — no change. Regression fixtures for the 4 ontology tools that depend on `ALL_ONTOLOGIES` ordering need regen with `--force-regen` per `feedback_kg_rebuild_regen_fixtures` workflow. **The rel-binding change will also touch fixtures for the existing 12 ontologies** — every regenerated fixture row will now carry 4 new null columns. This is expected; verify the change is "add 4 null columns to every row," nothing else. |

**Anti-scope-creep guardrail (mandatory in implementer briefs):** ADD only —
do not modify, rename, or rebaseline pre-existing ontology tests. If
`--force-regen` reveals a regression on the existing 12 ontologies that is
NOT explained by "added 4 null columns + rel binding," REPORT AS A CONCERN;
do not silently retune. The existing 12 ontologies' fixtures must change
only by appending the 4 null columns to every row, plus 2 new ontology
slots for `subcellular_localization` / `signal_peptide_type`.

---

## About-content updates (yaml)

Each of the 4 ontology-tool yamls gets:

1. **Description bump** (where the yaml lists supported ontologies) to
   mention `subcellular_localization` and `signal_peptide_type`.
2. **At least one new example** per yaml:
   - `search_ontology.yaml`: "Find the OuterMembrane localization"
     (`ontology="subcellular_localization"`, `search_text="outer"`).
   - `ontology_landscape.yaml`: include a sample row showing the two new
     ontologies in the `by_ontology` envelope at `level=0`.
   - `genes_by_ontology.yaml`: "PSORTb outer-membrane proteins with score"
     (`ontology="subcellular_localization"`, `term_ids=["psortb_OuterMembrane"]`,
     `organism="MED4"`) — show the `localization_score` column populated.
     Plus "Lipoproteins with cleavage info" (`ontology="signal_peptide_type"`,
     `term_ids=["signalp_LIPO"]`, `organism="MED4"`).
   - `gene_ontology_terms.yaml`: "Per-gene SignalP call with cleavage site"
     (`mode="leaf"`, `ontology="signal_peptide_type"`).
3. **Mistakes / chaining** entries:
   - "PSORTb / SignalP are **structural** ontologies — they describe *where*
     a gene's product lives, not *what it does*. Don't use them as
     functional-annotation proxies in `genes_by_function` `min_quality`
     reasoning."
   - "PSORTb / SignalP are flat (5 nodes each, single `level=0`). The
     `ontology_landscape` table returns one row per organism for each.
     Small N (5 categories) means `pathway_enrichment` may produce few
     significant results — this is expected, not a bug."
   - "`localization_score` / `signal_peptide_probability` are per-row
     edge properties; they're **only populated** when querying the matching
     ontology. Other ontology queries return null in those columns."

Run `uv run python scripts/build_about_content.py` after yaml edits to
regenerate the skills tree (per `feedback_skill_content_yaml_workflow`).

---

## Out-of-scope notes (file as backlog)

These could ride along but explicitly do NOT in this spec:

- **`gene_overview` exposing `subcellular_localization` / `signal_peptide_type`
  routing strings.** These are already on the Gene node and surface via
  `gene_details`. Per `project_dm_slice2_shipped` precedent, that's a
  "discovery surface routing-awareness" pass that touches multiple
  discovery tools — too scope-prone to bundle here.
- **`list_organisms` exposing `localization_count` / `signal_peptide_count`
  capability rollups.** Same reasoning.
- **`min_score` / `min_probability` filter params on `genes_by_ontology`.**
  Routing-signal extension; defer until a user actually asks. Today users
  can post-filter the returned rows or call `run_cypher`.
- **`pathway_enrichment` / `cluster_enrichment` validation against small-N
  ontologies.** Both will accept the new keys after the Literal bump, but
  with only 5 categories Fisher-test power is constrained. Phase 2 should
  add a smoke test confirming the call returns a well-formed envelope
  (even if no terms cross BH significance), not that it yields biologically
  meaningful enrichment.
- **Confidence-tier discovery via `list_filter_values`.** Could surface
  `localization_score` bucket boundaries / SignalP type distributions as
  filter facets. Defer.

---

## Implementation order (Phase 2)

1. **RED stage** — `test-updater` writes failing tests against
   `ALL_ONTOLOGIES = [..., "subcellular_localization", "signal_peptide_type"]`,
   the bumped Literals, and the 4 new optional row columns (including the
   "non-matching ontologies emit null" assertion).
2. **GREEN stage** — 4 implementer agents in parallel:
   - `query-builder`: add the 2 entries to `ONTOLOGY_CONFIG`. Modify
     `_hierarchy_walk`'s `bind_up` fragments to bind `[r:gene_rel]` (all
     variants: single-label, flat, bridge, pfam). Modify
     `_genes_by_ontology_match_stage` walk-down branches to also bind
     `r`, switch `collect(DISTINCT g)` → `collect(DISTINCT {g: g, r: r})`,
     and rewrite the UNWIND in `build_genes_by_ontology_detail` /
     `build_gene_ontology_terms_*` accordingly. Edge-prop columns derived
     once at build time from `ONTOLOGY_CONFIG` (union of all `edge_props`).
   - `api-updater`: verify `api/functions.py` reads `ALL_ONTOLOGIES`
     dynamically. Update row Pydantic models (or equivalent dicts) to
     include the 4 optional edge-prop fields.
   - `tool-wrapper`: bump the 5 `Literal`s + the `search_ontology`
     description in `mcp_server/tools.py`. Add 4 optional row-class fields
     for the new columns on `genes_by_ontology` and `gene_ontology_terms`.
   - `doc-updater`: append to `kg/constants.py` (new ontology entries),
     edit the 4 yamls, regen via `build_about_content.py`, update
     `CLAUDE.md` rows for `search_ontology` and `genes_by_ontology`.
3. **VERIFY stage** — code-review hard gate:
   - Live-Cypher correctness: confirm node-label spellings
     (`SubcellularLocalization` / `SignalPeptideType`), edge-type
     spellings (`Gene_has_subcellular_localization` /
     `Gene_has_signal_peptide_type`), fulltext-index names
     (`subcellularLocalizationFullText` / `signalPeptideTypeFullText`).
     These are the silent-failure mode per the `list_metabolites`
     smoke-test lesson.
   - Confirm rel-binding migration is transparent for the 12 pre-existing
     ontologies (regression fixtures change ONLY by adding 4 null columns
     + 2 new ontology slots; no row content alteration).
   - Confirm `localization_score` populated and other edge-prop columns
     null on PSORTb rows; mirror check on SignalP rows.
   - Confirm `gene_ontology_terms` `rollup` mode returns sensibly even
     though there's nothing to roll up (flat ontology) — should return
     the same rows as `leaf` mode at `level=0`.
   - Then unit + integration + regression with `--force-regen` for the
     4 ontology tools' landscape fixtures, then verified clean.

→ **Gate:** user approves this frozen spec. After approval, no
field/parameter additions without re-spec.
