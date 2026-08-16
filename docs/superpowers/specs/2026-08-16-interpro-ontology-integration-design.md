# InterPro as a first-class ontology in the explorer (W1)

**Date:** 2026-08-16
**Status:** Design — approved scope, implementation gated on the KG rebuild
**Driver:** `multiomics_biocypher_kg/docs/kg-changes/interproscan-extension.md`
**KG contract:** `…/docs/superpowers/specs/2026-08-16-vocabulary-contract-design.md` rev 5
**Asks / review record:** [docs/kg-specs/2026-08-16-interpro-tcdb-asks.md](../../kg-specs/2026-08-16-interpro-tcdb-asks.md) · [followup](../../kg-specs/2026-08-16-interpro-tcdb-followup-asks.md)
**Verified against:** KG `0.0.0-dev`, `built_at 2026-08-13T12:19:46.858Z`

---

## 1. Scope

Add InterPro to `ONTOLOGY_CONFIG` (bringing it to 15 keys), so it flows through the four
ontology tools and both enrichment tools with the same semantics as every other
ontology — plus the one thing InterPro does differently, `(interpro_type, level)` ORA
stratification.

**In scope**

- `InterproEntry` nodes + `Gene_has_interpro_entry` edges + `Interpro_entry_is_a_interpro_entry` hierarchy
- `search_ontology`, `ontology_landscape`, `genes_by_ontology`, `gene_ontology_terms`
- `pathway_enrichment`, `cluster_enrichment` (InterPro becomes a valid `ontology=`)
- `list_filter_values` — new `interpro_type` filter type
- `gene_overview` — `interpro_entry_count` routing signal
- Generated about-content for every touched tool

**Out of scope — backlogged, see [plans/backlog.md](../../../plans/backlog.md)**

| Item | Backlog entry |
|---|---|
| `Pfam_in_interpro_entry` bridge (5,972 edges) | B-01 |
| W2 provenance filters + `evidence` / `sources` surfacing | B-02 |
| W3 Layer-A router edges | B-03 |
| `ControlledVocabulary` contract adoption | B-04 |
| W4 TCDB regression bucket — **done before the release, not after** | B-05 |

**B-05 is release-coupled.** This spec ships first; the release must not be cut with
B-05 open.

---

## 2. The KG surface (verified, not assumed)

```cypher
MATCH (n:InterproEntry) RETURN count(n)                              // 12,999
MATCH ()-[r:Gene_has_interpro_entry]->() RETURN count(r)             // 397,342
MATCH ()-[r:Interpro_entry_is_a_interpro_entry]->() RETURN count(r)  // 1,569
MATCH (g:Gene) WHERE 'interpro' IN g.annotation_types RETURN count(g) // 102,895 (~85%)
```

**Node properties:** `interpro_id`, `name`, `interpro_type`, `level`, `gene_count`,
`organism_count`, `member_count`. Id prefix `interpro:` (a real bioregistry prefix,
unlike `psortb` / `signalp`). **No `level_kind`** — null by design, KG-IPT-003, shipped
as a `ControlledVocabulary` node with `expected_empty: true`.

**Edge properties:** `start`, `end` (domain envelope), `evalue`, `score`, `libraries`
(str[], 13 member DBs), `match_count`. `evalue` is **absent on 100,474 of 397,342 edges**
(25%) — HAMAP/PROSITE/PANTHER profile methods do not report one.

**Shape that drives the design:**

| Axis | Distribution |
|---|---|
| `level` | 0 → 11,430 (88%) · 1 → 1,490 · 2 → 79 |
| `interpro_type` | FAMILY 6,490 · DOMAIN 4,355 · HOMOLOGOUS_SUPERFAMILY 1,533 · CONSERVED_SITE 390 · ACTIVE_SITE 95 · REPEAT 74 · BINDING_SITE 55 · PTM 7 |
| `gene_count` | p50 **12** · p95 **94** · p99 **307** · max **6,909** (IPR027417, P-loop NTPase) |

**Indexes present:** `interproEntryFullText` (on `name`), `interpro_entry_id_idx`,
`interpro_entry_level_idx`, `interpro_entry_type_idx`. The last is the ORA key.

**Post-rebuild values** (this spec is written against these, per the §9.6 sequencing):
`interpro_type` and `libraries` become lowercase `snake_case`; `is_promiscuous` is
**deleted** — breadth is read as `gene_count >= 1000` (22 entries).

---

## 3. Design decisions

### D1 — `interpro_type` is an InterPro-specific filter, mirroring BRITE's `tree`

`ONTOLOGY_CONFIG` gains an `interpro` entry; the four ontology tools and both enrichment
tools gain `interpro_type: list[str] | None`, validated only when `ontology='interpro'`
and raising otherwise — the exact shape of the existing `tree` validation:

```python
if tree is not None and ontology != "brite":
    raise ValueError("tree filter is only valid for ontology='brite'")
```

**Rejected:** generalizing `tree` into a `partition` axis. It renames a live public MCP
param and conflates two different concepts — BRITE `tree` means *which hierarchy*,
`interpro_type` means *what kind of entity the entry is*.

**Why a list, not a scalar:** the primary use is stratified ORA
(`interpro_type=['family']`), and users will want FAMILY + DOMAIN together while
excluding HOMOLOGOUS_SUPERFAMILY. `tree` is scalar because a term belongs to one tree;
type-stratification is inherently a subset operation.

### D2 — `ontology_landscape` emits one row per `(interpro_type, level)`

`interpro_type` joins `tree` / `tree_code` as a **uniformly emitted, mostly-null**
column. This is not a new pattern: `build_ontology_landscape` already returns
`t.tree AS tree, t.tree_code AS tree_code` for every ontology, null outside BRITE, and
groups by them. Grouping by a uniformly-null column is a no-op, so **no other ontology's
row count or shape changes.**

```
WITH t.level AS level, t.tree AS tree, t.tree_code AS tree_code,
     t.interpro_type AS interpro_type,          # <-- added
     count(t) AS n_terms_with_genes, ...
ORDER BY level
```

Ordering becomes `ORDER BY level, interpro_type` so InterPro rows are stable.

**Consequence:** InterPro returns up to 8 × 3 = 24 rows where other ontologies return
one per level. In practice far fewer clear the `min_gene_set_size` gate. This is the
point — the KG doc is explicit that unstratified InterPro ORA is invalid.

### D3 — breadth is surfaced as a count, never as a default filter

`is_promiscuous` is deleted KG-side at rev 5 (derivable from `gene_count`, and hiding
that a judgement was made). The explorer therefore:

- surfaces `gene_count` on `search_ontology` / `ontology_landscape` rows (already the
  `n_genes_at_level` / per-term machinery),
- **does not** apply a promiscuity cutoff by default,
- documents the KG's advisory cutoff (`gene_count >= 1000` → 22 entries) in the
  about-content, so the number has a home the MCP can surface (KG-IPT-014 asks the KG
  to publish it as contract metadata; until then we quote it).

This satisfies KG-IPT-006 (breadth is advisory, never a default filter) structurally —
there is no flag to filter on.

The existing `min_gene_set_size` / `max_gene_set_size` params already bound term size
and need no change. Default `max_gene_set_size=500` happens to exclude IPR027417 (6,909)
and the other ultra-broad superfamilies from enrichment already.

### D4 — `informative_only` is a no-op for InterPro, and must say so

`scripts/post-import.cypher` excludes `interpro` from `informative_annotation_types`
because InterPro has no `is_uninformative` coverage (KG open item §10.4). Verified:

```cypher
MATCH (g:Gene) WHERE 'interpro' IN coalesce(g.informative_annotation_types,[])
RETURN count(g)     // 0
```

`informative_only=True` is the default on both enrichment tools and on
`ontology_landscape`. Its filter is `coalesce(t.is_uninformative,'') <> 'true'`, which
passes every InterPro entry — so the default is harmless but **silently does nothing**.

**Decision:** no code change; the filter stays uniform. The about-content states plainly
that `informative_only` has no effect for `ontology='interpro'` and that
`interpro_type` + `min/max_gene_set_size` are the real controls. Recorded as a KG
follow-up rather than worked around here.

### D5 — edge properties: surface the evidence payload, not the coordinates

`Gene_has_interpro_entry` carries six properties. The existing `edge_props` mechanism in
`ONTOLOGY_CONFIG` adds a column to **every** ontology's rows (null for non-owners), so
all six would widen every ontology row from 4 edge-prop columns to 10.

**Decision:** register only `libraries`, `evalue` and `score` as `edge_props` — the
evidence/ranking payload. `start` / `end` / `match_count` are domain coordinates that are
only meaningful gene-centrically, and go into `gene_ontology_terms` verbose output via a
dedicated projection.

**`evalue` is never a filter.** InterProScan pre-filters every match against each member
DB's curated threshold, and 25% of edges legitimately carry no `evalue` at all — a
threshold would silently drop every HAMAP/PROSITE/PANTHER hit. It is a **ranking key
only**, and the about-content must say so. No `min_evalue` / `max_evalue` param is added.

### D6 — `ALL_ONTOLOGIES` ordering

`kg/constants.py` documents the order as load-bearing for `ontology_landscape`
regression-fixture determinism. `interpro` is therefore **appended at the end** of the
list, after `signal_peptide_type`, so no existing fixture row order shifts.


```python
ALL_ONTOLOGIES = [
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam",
    "brite", "tcdb", "cazy",
    "subcellular_localization", "signal_peptide_type",
    "interpro",                                    # <-- appended
]
```

Note the CLAUDE.md tool table says `ontology_landscape` "surveys all 12 ontologies" while
`ALL_ONTOLOGIES` already has 14 entries — the docstring is stale independently of this
change and is corrected to 15 as part of the doc pass.

---

## 4. Per-layer changes

Per `.claude/skills/layer-rules`.

### 4.1 `kg/constants.py`

- `ALL_ONTOLOGIES` += `"interpro"` (D6).
- New `VALID_INTERPRO_TYPES: frozenset[str]` — the 8 lowercase values, for param
  validation. Vendored until B-04 makes it data-driven off `ControlledVocabulary`.
- `GO_ONTOLOGIES` unchanged (InterPro emits `best_effort_share=None`, like every non-GO
  ontology).

### 4.2 `kg/queries_lib.py`

`ONTOLOGY_CONFIG["interpro"]`:

```python
"interpro": {
    "label": "InterproEntry",
    "gene_rel": "Gene_has_interpro_entry",
    "hierarchy_rels": ["Interpro_entry_is_a_interpro_entry"],
    "fulltext_index": "interproEntryFullText",
    "edge_props": [
        ("libraries", "interpro_libraries"),
        ("evalue", "interpro_evalue"),
        ("score", "interpro_score"),
    ],
},
```

`_hierarchy_walk` needs **no special case** — InterPro is a plain single-label hierarchy
like EC or KEGG, so the generic `bind_up` / `walk_up` / `walk_down` fragments apply.

Builder changes, all following the `tree` precedent:

| Builder | Change |
|---|---|
| `build_search_ontology_summary` / `build_search_ontology` | `interpro_type` param + validation + `t.interpro_type IN $interpro_type` where-clause; emit `interpro_type` column |
| `build_genes_by_ontology_validate` / `_detail` / `_per_term` / `_per_gene` | same param + validation; where-clause applied after the hierarchy walk |
| `build_gene_ontology_terms_summary` / `build_gene_ontology_terms` | same param; emit `interpro_type` per row |
| `build_ontology_landscape` | D2 — add to GROUP BY + RETURN + ORDER BY |

### 4.3 `api/functions.py`

- Thread `interpro_type` through the six public functions.
- `ontology_landscape` envelope: new `by_interpro_type` rollup, populated only when
  `ontology='interpro'`.
- `search_ontology` / `genes_by_ontology` envelopes: `by_interpro_type` when applicable.
- `list_filter_values` gains `filter_type='interpro_type'`, returning the 8 values with
  per-value entry counts (`MATCH (n:InterproEntry) RETURN n.interpro_type, count(*)`).

### 4.4 `mcp_server/tools.py`

- `interpro_type: list[str] | None` on the six tools, with a description stating it is
  InterPro-only and is the **primary** ORA stratification axis.
- Row models gain `interpro_type: str | None` and the three edge-prop columns.
- `gene_overview`: surface `interpro_entry_count` (present on all 124,751 genes; 0 on the
  21,856 without InterPro) and add `'interpro'` to the `annotation_types` routing prose.
- `kg_schema` / docs resources: no change (schema is introspected live).

### 4.5 `inputs/tools/*.yaml` → regenerate

Touched: `search_ontology`, `ontology_landscape`, `genes_by_ontology`,
`gene_ontology_terms`, `pathway_enrichment`, `cluster_enrichment`,
`list_filter_values`, `gene_overview`.

Each needs `examples` / `mistakes` / `chaining` additions covering:

- **the ORA stratification rule** — `interpro_type` primary, `level` secondary; running
  unstratified lets P-loop NTPase (6,909 genes) dominate
- **`evalue` is a ranking key, never a filter** (D5), with the 25%-absent fact
- **`informative_only` is a no-op here** (D4)
- **`level` is nearly flat** — 88% of entries are level 0, so the usual level-rollup
  idiom does not transfer from GO/KEGG
- **no `level_kind`** — the column is null by contract, not by omission

Then: `uv run python scripts/build_about_content.py`.

### 4.6 `CLAUDE.md`

Tool table rows for the six tools; correct the stale "12 ontologies" to 15.

---

## 5. Testing

Per `.claude/skills/testing`.

**Unit (no Neo4j)** — `tests/unit/test_query_builders.py`
- `interpro` present in `ONTOLOGY_CONFIG`, `ALL_ONTOLOGIES`, `EXPECTED_TOOLS`
- `interpro_type` on a non-InterPro ontology raises `ValueError` (mirrors the `tree`
  tests exactly)
- an invalid `interpro_type` value raises, with the allowed set in the message
- generated Cypher contains `t.interpro_type IN $interpro_type` when set, and no
  `interpro_type` fragment when `None`
- `_edge_prop_return_columns()` yields the three new columns for every ontology, owned by
  `interpro`

**Unit** — `tests/unit/test_api_functions.py`, `test_tool_wrappers.py`: envelope
`by_interpro_type` present/absent by ontology; row model accepts null `interpro_type`.

**KG-marked (`pytest -m kg`)** — the numbers in §2 as assertions, plus:
- `genes_by_ontology(ontology='interpro', term_ids=['interpro:IPR027417'])` returns the
  P-loop NTPase set and is bounded by `max_gene_set_size`
- `ontology_landscape(ontology='interpro')` returns `(interpro_type, level)` rows with
  `level_kind IS NULL` on all of them
- **regression guard:** `ontology_landscape` row counts for all 14 pre-existing
  ontologies are byte-identical to the pre-change fixture (D2's no-op claim)

---

## 6. Implementation gate

Do not start until the rebuilt KG passes the entry criteria in
[the followup asks §6](../../kg-specs/2026-08-16-interpro-tcdb-followup-asks.md#6-sequencing--agreed-2026-08-16).
The two that matter for this spec:

```cypher
MATCH (n:InterproEntry) RETURN DISTINCT n.interpro_type
//   expect 8 lowercase snake_case values
MATCH ()-[r:Gene_has_interpro_entry]->() UNWIND r.libraries AS l RETURN DISTINCT l
//   expect 13 lowercase values
MATCH (n:InterproEntry) WHERE n.is_promiscuous IS NOT NULL RETURN count(*)
//   expect 0 (deleted at rev 5)
```

Structural counts that must be unchanged by the rename pass: `InterproEntry` 12,999 ·
`Gene_has_interpro_entry` 397,342 · hierarchy 1,569.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| D2 changes other ontologies' landscape rows | Explicit regression fixture over all 14 (§5); the null-grouping argument is a claim to be *tested*, not assumed |
| Row width grows for every ontology (D5) | Capped at 3 new columns; coordinates pushed to verbose |
| Users run unstratified InterPro ORA anyway | `interpro_type` is prominent in the tool description, and `max_gene_set_size=500` already excludes the worst offenders by default |
| `VALID_INTERPRO_TYPES` drifts from the KG | Vendored constant is a known stopgap; B-04 makes it data-driven |
