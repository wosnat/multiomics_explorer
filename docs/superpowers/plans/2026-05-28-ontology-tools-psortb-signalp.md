# PSORTb + SignalP ontology integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface `SubcellularLocalization` (PSORTb) and `SignalPeptideType` (SignalP) as flat scored ontologies across the 5 existing ontology tools, with edge-property columns (`localization_score`, `signal_peptide_probability`, `signal_peptide_cleavage_site`, `signal_peptide_cleavage_probability`) surfaced read-only on row-bearing tools.

**Architecture:** Mode-B cross-tool refresh. Two new entries in `ONTOLOGY_CONFIG` with a new optional `edge_props` field. Query builders bind the gene→leaf relationship (`-[r:gene_rel]->`) so edge properties can be projected. Two row Pydantic classes gain 4 optional fields. API layer strips sparse nulls (mirroring the existing `tree`/`tree_code` pattern). 5 `Literal[...]` enums on tool wrappers expand by 2 entries each. No new tools, no new filter params, no `annotation_types` / `annotation_quality` folding.

**Tech Stack:** Python 3.12, FastMCP, Pydantic v2, Neo4j Cypher, pytest. Generator: `scripts/build_about_content.py` writes the skills tree directly from `inputs/tools/*.yaml`.

**Spec reference:** [docs/tool-specs/ontology-tools-psortb-signalp.md](docs/tool-specs/ontology-tools-psortb-signalp.md)

---

## Pre-flight: Verify live KG

Run once before starting. If anything fails, stop and surface to the user — the KG side may not be live in this environment.

```bash
uv run python scripts/validate_connection.py
```

Then sanity-check the new ontology nodes + edges + fulltext indexes:

```bash
uv run multiomics-explorer cypher "MATCH (n:SubcellularLocalization) RETURN count(n) AS n_nodes"
# Expected: 5

uv run multiomics-explorer cypher "MATCH (n:SignalPeptideType) RETURN count(n) AS n_nodes"
# Expected: 5

uv run multiomics-explorer cypher "MATCH ()-[r:Gene_has_subcellular_localization]->() RETURN count(r) AS n_edges"
# Expected: 79361

uv run multiomics-explorer cypher "MATCH ()-[r:Gene_has_signal_peptide_type]->() RETURN count(r) AS n_edges"
# Expected: 13613

uv run multiomics-explorer cypher "CALL db.indexes() YIELD name WHERE name IN ['subcellularLocalizationFullText', 'signalPeptideTypeFullText'] RETURN name"
# Expected: both names returned
```

If counts differ from the spec's "Live KG observed counts (2026-05-27)" block, **stop** and confirm whether the KG has been rebuilt or whether the connected Neo4j instance is wrong. Do NOT silently rebaseline expected counts — that masks regressions.

---

## Task 1: ALL_ONTOLOGIES + ONTOLOGY_CONFIG entries (foundation)

**Files:**
- Modify: `multiomics_explorer/kg/constants.py:5-9`
- Modify: `multiomics_explorer/kg/queries_lib.py:10-98` (after the `cazy` entry)
- Test: `tests/unit/test_query_builders.py` (append two new test classes after `TestOntologyConfigCazy` at line 240)

- [ ] **Step 1.1: Write failing tests for `subcellular_localization` config**

Append to `tests/unit/test_query_builders.py` after the existing `TestOntologyConfigCazy` class:

```python
class TestOntologyConfigSubcellularLocalization:
    """subcellular_localization (PSORTb) ontology added to ONTOLOGY_CONFIG."""

    def test_subcellular_localization_in_ontology_config(self):
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        assert "subcellular_localization" in ONTOLOGY_CONFIG
        cfg = ONTOLOGY_CONFIG["subcellular_localization"]
        assert cfg["label"] == "SubcellularLocalization"
        assert cfg["gene_rel"] == "Gene_has_subcellular_localization"
        assert cfg["hierarchy_rels"] == []  # flat — no hierarchy
        assert cfg["fulltext_index"] == "subcellularLocalizationFullText"
        assert "bridge" not in cfg
        assert "parent_label" not in cfg
        # edge_props: list of (neo4j_prop, output_column) pairs
        assert cfg["edge_props"] == [("score", "localization_score")]

    def test_subcellular_localization_in_all_ontologies(self):
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert "subcellular_localization" in ALL_ONTOLOGIES

    def test_subcellular_localization_appended_after_cazy(self):
        """Order is load-bearing for regression-fixture determinism."""
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert ALL_ONTOLOGIES.index("subcellular_localization") > \
               ALL_ONTOLOGIES.index("cazy")


class TestOntologyConfigSignalPeptideType:
    """signal_peptide_type (SignalP) ontology added to ONTOLOGY_CONFIG."""

    def test_signal_peptide_type_in_ontology_config(self):
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        assert "signal_peptide_type" in ONTOLOGY_CONFIG
        cfg = ONTOLOGY_CONFIG["signal_peptide_type"]
        assert cfg["label"] == "SignalPeptideType"
        assert cfg["gene_rel"] == "Gene_has_signal_peptide_type"
        assert cfg["hierarchy_rels"] == []  # flat
        assert cfg["fulltext_index"] == "signalPeptideTypeFullText"
        assert "bridge" not in cfg
        assert "parent_label" not in cfg
        assert cfg["edge_props"] == [
            ("probability", "signal_peptide_probability"),
            ("cleavage_site", "signal_peptide_cleavage_site"),
            ("cleavage_probability", "signal_peptide_cleavage_probability"),
        ]

    def test_signal_peptide_type_in_all_ontologies(self):
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert "signal_peptide_type" in ALL_ONTOLOGIES

    def test_signal_peptide_type_appended_after_subcellular_localization(self):
        """Order is load-bearing."""
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert ALL_ONTOLOGIES.index("signal_peptide_type") > \
               ALL_ONTOLOGIES.index("subcellular_localization")


class TestEdgePropsAbsentOnOtherOntologies:
    """The `edge_props` field is optional. Existing 12 ontologies should
    not carry it (or carry empty list) so they emit nulls for the new
    edge-prop columns."""

    @pytest.mark.parametrize("ontology", [
        "go_bp", "go_mf", "go_cc", "ec", "kegg",
        "cog_category", "cyanorak_role", "tigr_role", "pfam",
        "brite", "tcdb", "cazy",
    ])
    def test_no_edge_props_on_pre_existing_ontologies(self, ontology):
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        cfg = ONTOLOGY_CONFIG[ontology]
        # Either absent or empty list — both signal "no edge props to surface"
        assert cfg.get("edge_props", []) == [], (
            f"Pre-existing ontology {ontology!r} unexpectedly has edge_props; "
            "only psortb/signalp should carry this field"
        )
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_query_builders.py -k "SubcellularLocalization or SignalPeptide or EdgePropsAbsent" -v`

Expected: 7 FAIL with KeyError or AssertionError on `"subcellular_localization" in ONTOLOGY_CONFIG` / `"signal_peptide_type" in ONTOLOGY_CONFIG`.

- [ ] **Step 1.3: Extend `ALL_ONTOLOGIES`**

Edit `multiomics_explorer/kg/constants.py` lines 5-9 — replace the list with:

```python
ALL_ONTOLOGIES: list[str] = [
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam",
    "brite", "tcdb", "cazy",
    "subcellular_localization", "signal_peptide_type",
]
```

- [ ] **Step 1.4: Append two entries to `ONTOLOGY_CONFIG`**

Edit `multiomics_explorer/kg/queries_lib.py` line 97 — directly after the `cazy` block's closing brace and before the closing `}` on line 98. Insert:

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

- [ ] **Step 1.5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_query_builders.py -k "SubcellularLocalization or SignalPeptide or EdgePropsAbsent" -v`

Expected: 7 PASS.

- [ ] **Step 1.6: Commit**

```bash
git add multiomics_explorer/kg/constants.py multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(kg): add subcellular_localization + signal_peptide_type to ONTOLOGY_CONFIG"
```

---

## Task 2: Edge-prop column helper (single source of truth)

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:98` (after `ONTOLOGY_CONFIG`)
- Test: `tests/unit/test_query_builders.py` (new test class)

- [ ] **Step 2.1: Write failing tests for the helper**

Append to `tests/unit/test_query_builders.py`:

```python
class TestEdgePropColumnHelper:
    """`_edge_prop_return_columns()` is the single source of truth for
    the ordered set of edge-prop output columns across all ontologies.
    Returns a list of (output_column, neo4j_prop, owner_ontology) tuples
    so the Cypher RETURN-builder can emit `r.<prop> AS <col>` for the
    owner and `null AS <col>` for non-owners.
    """

    def test_helper_returns_union_in_config_order(self):
        from multiomics_explorer.kg.queries_lib import _edge_prop_return_columns
        cols = _edge_prop_return_columns()
        # Order: subcellular_localization (1 col), then signal_peptide_type (3 cols)
        assert cols == [
            ("localization_score", "score", "subcellular_localization"),
            ("signal_peptide_probability", "probability", "signal_peptide_type"),
            ("signal_peptide_cleavage_site", "cleavage_site", "signal_peptide_type"),
            ("signal_peptide_cleavage_probability", "cleavage_probability",
             "signal_peptide_type"),
        ]

    def test_owner_cypher_for_psortb(self):
        """For the owner ontology, emit `r.<neo4j_prop> AS <output_column>`."""
        from multiomics_explorer.kg.queries_lib import _edge_prop_return_cypher
        cypher = _edge_prop_return_cypher("subcellular_localization")
        # Owner column: r.score AS localization_score
        # Non-owner columns: null AS <col>
        assert "r.score AS localization_score" in cypher
        assert "null AS signal_peptide_probability" in cypher
        assert "null AS signal_peptide_cleavage_site" in cypher
        assert "null AS signal_peptide_cleavage_probability" in cypher

    def test_owner_cypher_for_signalp(self):
        from multiomics_explorer.kg.queries_lib import _edge_prop_return_cypher
        cypher = _edge_prop_return_cypher("signal_peptide_type")
        assert "null AS localization_score" in cypher
        assert "r.probability AS signal_peptide_probability" in cypher
        assert "r.cleavage_site AS signal_peptide_cleavage_site" in cypher
        assert "r.cleavage_probability AS signal_peptide_cleavage_probability" \
            in cypher

    def test_non_owner_cypher_is_all_nulls(self):
        from multiomics_explorer.kg.queries_lib import _edge_prop_return_cypher
        cypher = _edge_prop_return_cypher("pfam")
        assert "null AS localization_score" in cypher
        assert "null AS signal_peptide_probability" in cypher
        assert "null AS signal_peptide_cleavage_site" in cypher
        assert "null AS signal_peptide_cleavage_probability" in cypher
        # No r.* projections for non-owner ontologies
        assert "r.score" not in cypher
        assert "r.probability" not in cypher
```

- [ ] **Step 2.2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_query_builders.py::TestEdgePropColumnHelper -v`

Expected: 4 FAIL with ImportError on `_edge_prop_return_columns` / `_edge_prop_return_cypher`.

- [ ] **Step 2.3: Implement the helpers**

Insert into `multiomics_explorer/kg/queries_lib.py` immediately after the `ONTOLOGY_CONFIG` dict (after line 98, before `def _hierarchy_walk`):

```python
def _edge_prop_return_columns() -> list[tuple[str, str, str]]:
    """Union of edge-prop columns across ONTOLOGY_CONFIG, in config order.

    Returns ordered list of (output_column, neo4j_prop, owner_ontology)
    triples. The list is the source of truth for column count, ordering,
    and column names — every ontology row must include each of these
    columns (with `r.<prop>` for the owner, `null` for non-owners) so
    the row schema is uniform across all ontologies.
    """
    cols: list[tuple[str, str, str]] = []
    for ont_key, cfg in ONTOLOGY_CONFIG.items():
        for neo4j_prop, output_col in cfg.get("edge_props", []):
            cols.append((output_col, neo4j_prop, ont_key))
    return cols


def _edge_prop_return_cypher(ontology: str) -> str:
    """Return a comma-prefixed Cypher fragment projecting edge-prop columns.

    For the owner ontology of each column, emits `r.<neo4j_prop> AS <col>`.
    For non-owner ontologies, emits `null AS <col>`. The relationship
    variable is assumed to be named `r` in the surrounding Cypher.

    Returned string starts with `,\n       ` so it can be appended directly
    after another RETURN-block column. Empty string if no edge_props are
    defined anywhere (defensive).
    """
    cols = _edge_prop_return_columns()
    if not cols:
        return ""
    parts: list[str] = []
    for output_col, neo4j_prop, owner in cols:
        if owner == ontology:
            parts.append(f"r.{neo4j_prop} AS {output_col}")
        else:
            parts.append(f"null AS {output_col}")
    return ",\n       " + ",\n       ".join(parts)
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_query_builders.py::TestEdgePropColumnHelper -v`

Expected: 4 PASS.

- [ ] **Step 2.5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(kg): add edge-prop column helpers for ontology query builders"
```

---

## Task 3: Bind relationship variable in `_hierarchy_walk` bind_up fragments

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:145-238` (the four `bind_up` constructions inside `_hierarchy_walk`)
- Test: `tests/unit/test_query_builders.py` (new test class)

- [ ] **Step 3.1: Write failing tests for rel binding**

Append to `tests/unit/test_query_builders.py`:

```python
class TestHierarchyWalkRelBinding:
    """`_hierarchy_walk`'s `bind_up` fragment must bind the gene→leaf
    relationship as `r` so consumers can project edge properties.
    Applies to all variants: single-label, flat, bridge, pfam."""

    def test_single_label_binds_r(self):
        """e.g. tcdb (single-label tree)."""
        frag = _hierarchy_walk("tcdb", direction="up")
        assert "[r:Gene_has_tcdb_family]" in frag["bind_up"], (
            f"Expected [r:Gene_has_tcdb_family] in bind_up; "
            f"got: {frag['bind_up']!r}"
        )

    def test_flat_ontology_binds_r(self):
        """e.g. cog_category (flat) — also covers the new
        subcellular_localization and signal_peptide_type."""
        frag = _hierarchy_walk("cog_category", direction="up")
        assert "[r:Gene_in_cog_category]" in frag["bind_up"]

    def test_subcellular_localization_binds_r(self):
        frag = _hierarchy_walk("subcellular_localization", direction="up")
        assert "[r:Gene_has_subcellular_localization]" in frag["bind_up"]

    def test_signal_peptide_type_binds_r(self):
        frag = _hierarchy_walk("signal_peptide_type", direction="up")
        assert "[r:Gene_has_signal_peptide_type]" in frag["bind_up"]

    def test_bridge_binds_r_on_first_hop(self):
        """BRITE (bridge: gene→KeggTerm→BriteCategory). Bind r on the
        gene→kegg-term edge (the gene_rel), not the bridge edge."""
        frag = _hierarchy_walk("brite", direction="up")
        assert "[r:Gene_has_kegg_ko]" in frag["bind_up"], (
            f"Expected [r:Gene_has_kegg_ko] (the gene_rel) bound in bridge "
            f"bind_up; got: {frag['bind_up']!r}"
        )

    def test_pfam_binds_r(self):
        frag = _hierarchy_walk("pfam", direction="up")
        assert "[r:Gene_has_pfam]" in frag["bind_up"]
```

- [ ] **Step 3.2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_query_builders.py::TestHierarchyWalkRelBinding -v`

Expected: 6 FAIL — current `bind_up` uses unbound `-[:gene_rel]->`.

- [ ] **Step 3.3: Modify the four `bind_up` constructions**

Edit `multiomics_explorer/kg/queries_lib.py` — in `_hierarchy_walk` change each `bind_up` assignment to bind `r`. Four sites:

**Site A — Pfam branch (line 146-149):**

```python
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[r:{gene_rel}]->(leaf:Pfam)"
        )
```

**Site B — Bridge branch (line 197-201):**

```python
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[r:{gene_rel}]->(ko:{bridge_node})"
            f"-[:{bridge_edge}]->(leaf:{leaf_label})"
        )
```

(Bind `r` on the gene→bridge-node edge only; the bridge edge stays unbound.)

**Site C — Flat ontologies branch (line 217-220):**

```python
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[r:{gene_rel}]->(t:{leaf_label})"
        )
```

**Site D — Single-label tree branch (line 231-234):**

```python
    bind_up = (
        f"MATCH (g:Gene {{organism_name: $org}})"
        f"-[r:{gene_rel}]->(leaf:{leaf_label})"
    )
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_query_builders.py::TestHierarchyWalkRelBinding -v`

Expected: 6 PASS.

Also run any pre-existing hierarchy-walk tests:

Run: `uv run pytest tests/unit/test_query_builders.py -k "HierarchyWalk" -v`

Expected: ALL pass (existing tests should still pass — they assert string substrings that don't conflict with rel binding; if any does, READ the failing test before changing it — it may be asserting the OLD unbound form, in which case update the assertion to match the new bound form).

- [ ] **Step 3.5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "refactor(kg): bind gene-rel as r in _hierarchy_walk bind_up fragments"
```

---

## Task 4: `_genes_by_ontology_match_stage` — bind r in mode-1 walk-down + collect `{g, r}` records

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:2212-2316` (entire `_genes_by_ontology_match_stage`)
- Test: `tests/unit/test_query_builders.py` (new test class)

This is the highest-leverage code change: every detail/per-term/per-gene query routes through here.

- [ ] **Step 4.1: Write failing tests for new collect shape and walk-down rel binding**

Append to `tests/unit/test_query_builders.py`:

```python
class TestMatchStageRelBinding:
    """`_genes_by_ontology_match_stage` must bind `r` in BOTH mode-1
    walk-down (where bind happens inside the helper) and modes 2/3
    walk-up (where bind comes from `_hierarchy_walk.bind_up`). The
    final collect must collect `{g: g, r: r}` records so the detail
    builder can project edge properties."""

    def test_mode_1_walk_down_binds_r_for_flat_ontology(self):
        """Mode 1 (term_ids only) for subcellular_localization."""
        from multiomics_explorer.kg.queries_lib import _genes_by_ontology_match_stage
        cypher, _ = _genes_by_ontology_match_stage(
            ontology="subcellular_localization",
            level=None, term_ids=["psortb_OuterMembrane"],
            organism="MED4",
        )
        assert "[r:Gene_has_subcellular_localization]" in cypher

    def test_mode_1_walk_down_binds_r_for_single_label_tree(self):
        """Mode 1 for tcdb (single-label tree)."""
        from multiomics_explorer.kg.queries_lib import _genes_by_ontology_match_stage
        cypher, _ = _genes_by_ontology_match_stage(
            ontology="tcdb",
            level=None, term_ids=["tcdb:1.A.1"],
            organism="MED4",
        )
        assert "[r:Gene_has_tcdb_family]" in cypher

    def test_mode_2_walk_up_binds_r_via_bind_up(self):
        """Mode 2 (level only) — bind_up from _hierarchy_walk carries r."""
        from multiomics_explorer.kg.queries_lib import _genes_by_ontology_match_stage
        cypher, _ = _genes_by_ontology_match_stage(
            ontology="signal_peptide_type",
            level=0, term_ids=None,
            organism="MED4",
        )
        assert "[r:Gene_has_signal_peptide_type]" in cypher

    def test_collect_emits_g_r_records(self):
        """The final collect step must produce {g, r} records, not bare g."""
        from multiomics_explorer.kg.queries_lib import _genes_by_ontology_match_stage
        cypher, _ = _genes_by_ontology_match_stage(
            ontology="tcdb",
            level=None, term_ids=["tcdb:1.A.1"],
            organism="MED4",
        )
        # New shape — drops the legacy `collect(DISTINCT g) AS term_genes`
        assert "collect(DISTINCT {g: g, r: r}) AS term_genes" in cypher
        # Guard the legacy shape doesn't linger
        assert "collect(DISTINCT g) AS term_genes" not in cypher
```

- [ ] **Step 4.2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_query_builders.py::TestMatchStageRelBinding -v`

Expected: 4 FAIL — mode-1 walk-down still unbound; collect still bare `g`.

- [ ] **Step 4.3: Modify `_genes_by_ontology_match_stage`**

Edit `multiomics_explorer/kg/queries_lib.py` lines 2212-2316. The function body has two mode branches and a final collect. Update:

**Mode 1 walk-down — pfam branch (lines 2245-2255):**

```python
        if ontology == "pfam":
            cypher_head = (
                "UNWIND $term_ids AS input_tid\n"
                "OPTIONAL MATCH (tp:Pfam {id: input_tid})\n"
                "OPTIONAL MATCH (tc:PfamClan {id: input_tid})\n"
                "WITH input_tid, coalesce(tp, tc) AS t\n"
                "OPTIONAL MATCH (t)<-[:Pfam_in_pfam_clan*0..1]-(leaf:Pfam)\n"
                "WITH t, coalesce(leaf, t) AS leaf\n"
                "MATCH (g:Gene {organism_name: $org})-[r:Gene_has_pfam]->(leaf)\n"
                "WHERE t:Pfam OR t:PfamClan\n"
            )
```

**Mode 1 walk-down — single-label / flat branch (lines 2262-2277):**

```python
            frag = _hierarchy_walk(ontology, direction="down")
            leaf = frag["leaf_label"]
            walk = frag["walk_down"]
            if walk:
                cypher_head = (
                    "UNWIND $term_ids AS input_tid\n"
                    f"MATCH (t:{leaf} {{id: input_tid}})\n"
                    f"{walk}\n"
                    f"MATCH (g:Gene {{organism_name: $org}})"
                    f"-[r:{frag['gene_rel']}]->(leaf)\n"
                )
            else:
                cypher_head = (
                    "UNWIND $term_ids AS input_tid\n"
                    f"MATCH (t:{leaf} {{id: input_tid}})\n"
                    f"MATCH (g:Gene {{organism_name: $org}})"
                    f"-[r:{frag['gene_rel']}]->(t)\n"
                )
```

(The bridge case for `brite` Mode 1 lives in `_hierarchy_walk.walk_down`; the gene→bridge-node hop happens AFTER the walk, in the MATCH (g)…(leaf) line, where `leaf` is the bridge node for BRITE. Bind `r` on that gene→bridge-node edge — same `frag['gene_rel']` substitution. The bridge edge inside `walk_down` stays unbound. ✓ already handled by the line above.)

**Mode 2/3 walk-up:** unchanged Cypher source code — `bind` already comes from `_hierarchy_walk.bind_up` (which was bound to `r` in Task 3). No edit needed here.

**Final collect (line ~2310-2315):**

Change:
```python
    size_filter = (
        "WITH t, collect(DISTINCT g) AS term_genes\n"
        "WHERE size(term_genes) >= $min_gene_set_size\n"
        "  AND ($max_gene_set_size IS NULL OR "
        "size(term_genes) <= $max_gene_set_size)"
    )
```

To:
```python
    size_filter = (
        "WITH t, collect(DISTINCT {g: g, r: r}) AS term_genes\n"
        "WHERE size(term_genes) >= $min_gene_set_size\n"
        "  AND ($max_gene_set_size IS NULL OR "
        "size(term_genes) <= $max_gene_set_size)"
    )
```

**Informative filter (line ~2303-2306):**

The current informative filter is:
```python
    informative_filter = (
        "WITH t, g WHERE coalesce(t.is_uninformative, '') <> 'true'\n"
        if informative_only else ""
    )
```

Change to carry `r` through:
```python
    informative_filter = (
        "WITH t, g, r WHERE coalesce(t.is_uninformative, '') <> 'true'\n"
        if informative_only else ""
    )
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_query_builders.py::TestMatchStageRelBinding -v`

Expected: 4 PASS.

Also run the broader query-builder suite to catch anything that's now broken:

Run: `uv run pytest tests/unit/test_query_builders.py -v`

Expected: any new failures here belong to the per_term/per_gene/detail builders (Tasks 5–6 will fix them). Failures in unrelated test classes are real — investigate before continuing.

- [ ] **Step 4.5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "refactor(kg): bind r in match_stage walk-down; collect {g,r} records"
```

---

## Task 5: Update `build_genes_by_ontology_per_term` and `build_genes_by_ontology_per_gene` to consume `{g, r}` records

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:2397-2441` (per_term)
- Modify: `multiomics_explorer/kg/queries_lib.py:2444-2481` (per_gene)
- Test: `tests/unit/test_query_builders.py`

These two aggregate builders don't need edge-prop columns themselves — they just need to consume the new collect shape. Aliasing `pair.g AS g` keeps the downstream Cypher identical.

- [ ] **Step 5.1: Write failing tests asserting the new UNWIND shape**

Append to `tests/unit/test_query_builders.py`:

```python
class TestPerTermPerGeneUnwindShape:
    """After Task 4's collect-shape change, per_term and per_gene must
    UNWIND `{g, r}` records and alias `pair.g AS g` so their downstream
    Cypher is identical."""

    def test_per_term_unwinds_pair_with_g_alias(self):
        from multiomics_explorer.kg.queries_lib import build_genes_by_ontology_per_term
        cypher, _ = build_genes_by_ontology_per_term(
            ontology="tcdb", organism="MED4",
            level=None, term_ids=["tcdb:1.A.1"],
        )
        # New: unwind to pair, alias to g (and r — even if unused — to
        # preserve symmetry)
        assert "UNWIND term_genes AS pair" in cypher
        assert "pair.g AS g" in cypher
        # Guard: bare-g UNWIND must be gone
        assert "UNWIND term_genes AS g\n" not in cypher

    def test_per_gene_unwinds_pair_with_g_alias(self):
        from multiomics_explorer.kg.queries_lib import build_genes_by_ontology_per_gene
        cypher, _ = build_genes_by_ontology_per_gene(
            ontology="cog_category", organism="MED4",
            level=0, term_ids=None,
        )
        assert "UNWIND term_genes AS pair" in cypher
        assert "pair.g AS g" in cypher
        assert "UNWIND term_genes AS g\n" not in cypher
```

- [ ] **Step 5.2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_query_builders.py::TestPerTermPerGeneUnwindShape -v`

Expected: 2 FAIL.

- [ ] **Step 5.3: Update `build_genes_by_ontology_per_term`**

Edit `multiomics_explorer/kg/queries_lib.py` lines 2428-2440. Replace the `tail` with:

```python
    tail = (
        "UNWIND term_genes AS pair\n"
        "WITH t, pair.g AS g, pair.r AS r\n"
        "WITH t, collect({lt: g.locus_tag, "
        "cat: coalesce(g.gene_category, 'Unknown')}) AS gene_rows\n"
        "RETURN t.id AS term_id, t.name AS term_name, t.level AS level,\n"
        "       t.tree AS tree, t.tree_code AS tree_code,\n"
        "       t.level_is_best_effort IS NOT NULL AS best_effort,\n"
        "       size(gene_rows) AS n_genes,\n"
        "       apoc.coll.frequencies("
        "[row IN gene_rows | row.cat]) AS cat_freqs,\n"
        "       coalesce(t.is_uninformative, '') <> 'true' AS is_informative\n"
        "ORDER BY t.id"
    )
```

(Note: renamed the inner list-comprehension variable from `r` to `row` to avoid shadowing the rel `r` after the alias step.)

- [ ] **Step 5.4: Update `build_genes_by_ontology_per_gene`**

Edit `multiomics_explorer/kg/queries_lib.py` lines 2471-2480. Replace the `tail` with:

```python
    tail = (
        "UNWIND term_genes AS pair\n"
        "WITH t, pair.g AS g, pair.r AS r\n"
        "WITH g, collect(DISTINCT t.id) AS gene_terms, "
        "collect(DISTINCT t.level) AS gene_levels\n"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       coalesce(g.gene_category, 'Unknown') AS gene_category,\n"
        "       size(gene_terms) AS n_terms,\n"
        "       gene_levels AS levels_hit\n"
        "ORDER BY g.locus_tag"
    )
```

- [ ] **Step 5.5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_query_builders.py::TestPerTermPerGeneUnwindShape -v`

Expected: 2 PASS.

Run pre-existing per_term/per_gene tests:

Run: `uv run pytest tests/unit/test_query_builders.py -k "per_term or per_gene" -v`

Expected: ALL pass (the public RETURN shape of per_term/per_gene is unchanged — `term_id`, `term_name`, `n_genes`, etc. — so api/-level tests don't need to change).

- [ ] **Step 5.6: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "refactor(kg): per_term/per_gene consume new {g,r} collect shape"
```

---

## Task 6: `build_genes_by_ontology_detail` — emit edge-prop columns

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:2319-2394` (detail builder)
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 6.1: Write failing tests for edge-prop column emission**

Append to `tests/unit/test_query_builders.py`:

```python
class TestGenesByOntologyDetailEdgeProps:
    """build_genes_by_ontology_detail must emit edge-prop columns:
    `r.<prop> AS <output_col>` on the owner ontology, `null AS <col>`
    on all other ontologies. Row schema is uniform across all 14
    ontologies."""

    def test_subcellular_localization_emits_localization_score(self):
        from multiomics_explorer.kg.queries_lib import build_genes_by_ontology_detail
        cypher, _ = build_genes_by_ontology_detail(
            ontology="subcellular_localization",
            organism="MED4",
            term_ids=["psortb_OuterMembrane"],
        )
        assert "r.score AS localization_score" in cypher
        # Other-ontology columns are null on this query
        assert "null AS signal_peptide_probability" in cypher
        assert "null AS signal_peptide_cleavage_site" in cypher
        assert "null AS signal_peptide_cleavage_probability" in cypher

    def test_signal_peptide_type_emits_three_signalp_cols(self):
        from multiomics_explorer.kg.queries_lib import build_genes_by_ontology_detail
        cypher, _ = build_genes_by_ontology_detail(
            ontology="signal_peptide_type",
            organism="MED4",
            term_ids=["signalp_LIPO"],
        )
        assert "r.probability AS signal_peptide_probability" in cypher
        assert "r.cleavage_site AS signal_peptide_cleavage_site" in cypher
        assert "r.cleavage_probability AS signal_peptide_cleavage_probability" in cypher
        assert "null AS localization_score" in cypher

    def test_pfam_emits_all_nulls(self):
        """Non-owner ontology — all 4 edge-prop columns null."""
        from multiomics_explorer.kg.queries_lib import build_genes_by_ontology_detail
        cypher, _ = build_genes_by_ontology_detail(
            ontology="pfam",
            organism="MED4",
            term_ids=["pfam:PF00001"],
        )
        assert "null AS localization_score" in cypher
        assert "null AS signal_peptide_probability" in cypher
        assert "null AS signal_peptide_cleavage_site" in cypher
        assert "null AS signal_peptide_cleavage_probability" in cypher
        assert "r.score" not in cypher
        assert "r.probability" not in cypher

    def test_detail_unwinds_pair_with_g_r_alias(self):
        """After Task 4's collect change, detail must UNWIND `pair` and
        alias `pair.g AS g, pair.r AS r`."""
        from multiomics_explorer.kg.queries_lib import build_genes_by_ontology_detail
        cypher, _ = build_genes_by_ontology_detail(
            ontology="tcdb",
            organism="MED4",
            term_ids=["tcdb:1.A.1"],
        )
        assert "UNWIND term_genes AS pair" in cypher
        assert "pair.g AS g" in cypher
        assert "pair.r AS r" in cypher
```

- [ ] **Step 6.2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_query_builders.py::TestGenesByOntologyDetailEdgeProps -v`

Expected: 4 FAIL.

- [ ] **Step 6.3: Update `build_genes_by_ontology_detail`**

Edit `multiomics_explorer/kg/queries_lib.py` lines 2319-2394. Two parts:

**Part A — emit edge-prop column block in RETURN.** Replace the return block construction (lines 2363-2377):

```python
    # Row return
    verbose_cols = (
        ",\n       g.function_description AS function_description,\n"
        "       t.level_is_best_effort IS NOT NULL AS level_is_best_effort"
        if verbose else ""
    )
    edge_prop_cols = _edge_prop_return_cypher(ontology)
    return_block = (
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_category AS gene_category,\n"
        "       t.id AS term_id, t.name AS term_name, t.level AS level,\n"
        "       t.tree AS tree, t.tree_code AS tree_code,\n"
        "       coalesce(t.is_uninformative, '') <> 'true' AS is_informative"
        f"{verbose_cols}{edge_prop_cols}\n"
        "ORDER BY t.id, g.locus_tag"
    )
```

**Part B — change UNWIND from `g` to `pair` with alias.** Replace the cypher-assembly line (lines 2389-2393):

```python
    cypher = (
        f"{head}\n"
        f"UNWIND term_genes AS pair\n"
        f"WITH t, pair.g AS g, pair.r AS r\n"
        f"{return_block}{skip_clause}{limit_clause}"
    )
```

- [ ] **Step 6.4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_query_builders.py::TestGenesByOntologyDetailEdgeProps -v`

Expected: 4 PASS.

Run pre-existing detail builder tests:

Run: `uv run pytest tests/unit/test_query_builders.py -k "detail" -v`

Expected: ALL pass. If a pre-existing test asserts the exact RETURN-block string verbatim and now fails because of the appended `, r.score AS localization_score, null AS ...` columns, **update the assertion** to include the new column block — but ONLY add columns; do not modify the pre-existing assertion text.

- [ ] **Step 6.5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(kg): emit edge-prop columns in build_genes_by_ontology_detail"
```

---

## Task 7: `build_gene_ontology_terms` — bind r + emit edge-prop columns (both modes)

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:2677-2838` (full `build_gene_ontology_terms`)
- Test: `tests/unit/test_query_builders.py`

This builder does NOT use `_genes_by_ontology_match_stage` — it has its own match-and-return logic for both `leaf` and `rollup` modes. Both modes need direct rel binding and edge-prop columns.

- [ ] **Step 7.1: Write failing tests**

Append to `tests/unit/test_query_builders.py`:

```python
class TestGeneOntologyTermsRelBindingAndEdgeProps:
    """build_gene_ontology_terms binds r and emits edge-prop columns in
    BOTH leaf and rollup modes."""

    # --- leaf mode ---

    def test_leaf_mode_binds_r(self):
        from multiomics_explorer.kg.queries_lib import build_gene_ontology_terms
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="subcellular_localization",
            organism_name="MED4", mode="leaf",
        )
        assert "[r:Gene_has_subcellular_localization]" in cypher

    def test_leaf_mode_emits_owner_edge_prop(self):
        from multiomics_explorer.kg.queries_lib import build_gene_ontology_terms
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="signal_peptide_type",
            organism_name="MED4", mode="leaf",
        )
        assert "r.probability AS signal_peptide_probability" in cypher
        assert "r.cleavage_site AS signal_peptide_cleavage_site" in cypher
        assert "r.cleavage_probability AS signal_peptide_cleavage_probability" in cypher
        assert "null AS localization_score" in cypher

    def test_leaf_mode_non_owner_emits_all_nulls(self):
        from multiomics_explorer.kg.queries_lib import build_gene_ontology_terms
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="pfam",
            organism_name="MED4", mode="leaf",
        )
        assert "null AS localization_score" in cypher
        assert "null AS signal_peptide_probability" in cypher
        assert "null AS signal_peptide_cleavage_site" in cypher
        assert "null AS signal_peptide_cleavage_probability" in cypher
        assert "r.score" not in cypher
        assert "r.probability" not in cypher

    # --- rollup mode ---

    def test_rollup_mode_binds_r(self):
        from multiomics_explorer.kg.queries_lib import build_gene_ontology_terms
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="subcellular_localization",
            organism_name="MED4", mode="rollup", level=0,
        )
        assert "[r:Gene_has_subcellular_localization]" in cypher

    def test_rollup_mode_emits_owner_edge_prop(self):
        from multiomics_explorer.kg.queries_lib import build_gene_ontology_terms
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="subcellular_localization",
            organism_name="MED4", mode="rollup", level=0,
        )
        assert "r.score AS localization_score" in cypher

    def test_rollup_mode_flat_keeps_r_in_with_scope(self):
        """The flat-branch rollup `walk` includes a WITH stage; r must
        be preserved through it so the RETURN can project r.score."""
        from multiomics_explorer.kg.queries_lib import build_gene_ontology_terms
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="subcellular_localization",
            organism_name="MED4", mode="rollup", level=0,
        )
        # Must keep r through the WITH stage (otherwise RETURN r.score crashes)
        assert "WITH g, t, r" in cypher
        # Guard the legacy 2-var WITH doesn't linger
        assert "WITH g, t\nWHERE" not in cypher

    def test_rollup_mode_non_owner_emits_all_nulls(self):
        from multiomics_explorer.kg.queries_lib import build_gene_ontology_terms
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="tcdb",
            organism_name="MED4", mode="rollup", level=0,
        )
        assert "null AS localization_score" in cypher
        assert "null AS signal_peptide_probability" in cypher
```

- [ ] **Step 7.2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_query_builders.py::TestGeneOntologyTermsRelBindingAndEdgeProps -v`

Expected: 7 FAIL.

- [ ] **Step 7.3: Update `build_gene_ontology_terms` — bind r on all MATCH clauses**

Edit `multiomics_explorer/kg/queries_lib.py` lines 2677-2838. There are 5 MATCH clauses across leaf and rollup modes that bind gene→leaf:

**Rollup-mode, bridge branch (lines 2735-2738):**

```python
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(ko:{bridge_node})"
                f"-[:{bridge_edge}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
```

**Rollup-mode, flat branch (lines 2748-2753):**

```python
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            walk = "WITH g, t, r\nWHERE t.level = $level\n"
```

**Important:** the flat-branch `walk` (line 2753) currently reads `"WITH g, t\nWHERE t.level = $level\n"` — that `WITH g, t` projection drops the newly-bound `r` from scope, breaking the RETURN-block projection of `r.<edge_prop>`. Replace with `"WITH g, t, r\nWHERE t.level = $level\n"` so `r` survives.

**Rollup-mode, pfam branch (lines 2755-2759):**

```python
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(leaf:Pfam)\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
```

**Rollup-mode, single-label tree (lines 2766-2770):**

```python
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
```

**Leaf-mode, bridge branch (lines 2798-2803):**

```python
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
```

**Leaf-mode, non-bridge branch (lines 2805-2808):**

```python
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})-[r:{gene_rel}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
```

- [ ] **Step 7.4: Append edge-prop columns to both RETURN blocks**

Inside `build_gene_ontology_terms`, before the rollup-mode and leaf-mode `cypher = ...` assignments, compute the edge-prop columns once near the top of the function (right after the `verbose_cols` assignment at line 2711-2714):

```python
    verbose_cols = (
        ",\n       g.organism_name AS organism_name"
        if verbose else ""
    )
    edge_prop_cols = _edge_prop_return_cypher(ontology)
```

Then update the two RETURN blocks to append `{edge_prop_cols}`:

**Rollup-mode RETURN (line 2788-2791):**

```python
            "RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id,\n"
            f"       t.name AS term_name, t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
            f"       coalesce(t.is_uninformative, '') <> 'true' AS is_informative{verbose_cols}{edge_prop_cols}\n"
            f"ORDER BY g.locus_tag, t.id{skip_clause}{limit_clause}"
```

**Leaf-mode RETURN (line 2833-2836):**

```python
            "RETURN g.locus_tag AS locus_tag, t.id AS term_id,\n"
            f"       t.name AS term_name, t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
            f"       coalesce(t.is_uninformative, '') <> 'true' AS is_informative{verbose_cols}{edge_prop_cols}\n"
            f"ORDER BY g.locus_tag, t.id{skip_clause}{limit_clause}"
```

**Important caveat for rollup mode:** in rollup mode the `r` rel is bound from the gene→leaf edge, but the RETURN refers to `t` (the ancestor, possibly = leaf for flat / a true ancestor for tree). For PSORTb / SignalP (flat) `t = leaf`, so `r.score` is the right gene→leaf score. For tree ontologies (which have no `edge_props`), the edge-prop columns are all null anyway — so the projection is harmless. ✓

- [ ] **Step 7.5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_query_builders.py::TestGeneOntologyTermsRelBindingAndEdgeProps -v`

Expected: 7 PASS.

Run pre-existing gene_ontology_terms tests:

Run: `uv run pytest tests/unit/test_query_builders.py -k "gene_ontology_terms" -v`

Expected: ALL pass.

- [ ] **Step 7.6: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(kg): bind r + emit edge-prop columns in build_gene_ontology_terms"
```

---

## Task 8: API layer — strip sparse edge-prop nulls on non-owner rows

**Files:**
- Modify: `multiomics_explorer/api/functions.py:1751-1755` (`genes_by_ontology` post-process)
- Modify: `multiomics_explorer/api/functions.py` (`gene_ontology_terms` post-process — locate via grep below)
- Test: `tests/unit/test_api_functions.py`

The detail rows now carry 4 edge-prop columns. On non-owner ontologies they're all null. Strip them post-query so the wire payload stays clean — mirrors the existing `tree` / `tree_code` strip pattern.

- [ ] **Step 8.1: Locate the strip site in `gene_ontology_terms`**

Run: `grep -n "tree.*None\|r.pop" multiomics_explorer/api/functions.py | head -20`

Find the analogous strip block (likely near line 1900-2000). If none exists, add the strip in the row-iteration block where results are assembled.

- [ ] **Step 8.2: Write failing tests asserting null-stripping**

Append to `tests/unit/test_api_functions.py` (use existing test fixtures / conn mocks following the same pattern as the `tree` strip tests):

```python
class TestGenesByOntologyEdgePropStripping:
    """Non-owner ontologies must have edge-prop columns stripped from rows.
    Mirrors the `tree`/`tree_code` strip pattern."""

    def test_non_owner_ontology_strips_edge_prop_columns(
        self, mock_conn_with_genes_by_ontology
    ):
        """When querying ontology='pfam', the edge-prop columns must NOT
        appear in any row of the response."""
        from multiomics_explorer.api.functions import genes_by_ontology
        result = genes_by_ontology(
            ontology="pfam", organism="MED4",
            term_ids=["pfam:PF00001"],
            conn=mock_conn_with_genes_by_ontology,
        )
        for row in result["results"]:
            assert "localization_score" not in row
            assert "signal_peptide_probability" not in row
            assert "signal_peptide_cleavage_site" not in row
            assert "signal_peptide_cleavage_probability" not in row

    def test_owner_ontology_psortb_keeps_localization_score(
        self, mock_conn_with_psortb_genes_by_ontology
    ):
        """When querying ontology='subcellular_localization', the
        localization_score column survives; the other 3 (signalp cols)
        are stripped."""
        from multiomics_explorer.api.functions import genes_by_ontology
        result = genes_by_ontology(
            ontology="subcellular_localization", organism="MED4",
            term_ids=["psortb_OuterMembrane"],
            conn=mock_conn_with_psortb_genes_by_ontology,
        )
        for row in result["results"]:
            assert "localization_score" in row
            assert isinstance(row["localization_score"], (int, float))
            assert "signal_peptide_probability" not in row
            assert "signal_peptide_cleavage_site" not in row
            assert "signal_peptide_cleavage_probability" not in row
```

(Implementation hint: use existing mock-conn fixture patterns from `tests/unit/test_api_functions.py` — if no usable fixture exists, create the minimal one that returns rows with the 4 new columns. Pattern: feed canned `per_term` / `per_gene` / `detail` row dicts via a fake `execute_query`.)

- [ ] **Step 8.3: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_api_functions.py::TestGenesByOntologyEdgePropStripping -v`

Expected: 2 FAIL.

- [ ] **Step 8.4: Update `genes_by_ontology` post-process**

Edit `multiomics_explorer/api/functions.py` around line 1751-1755 (the existing `tree`/`tree_code` strip block). Replace:

```python
    # Strip sparse tree/tree_code for non-BRITE results
    for r in results:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)
```

With:

```python
    # Strip sparse tree/tree_code for non-BRITE results
    for r in results:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)

    # Strip sparse edge-prop columns when their value is null. Owner ontology
    # keeps its non-null column; non-owner rows shed all of them.
    _EDGE_PROP_COLS = (
        "localization_score",
        "signal_peptide_probability",
        "signal_peptide_cleavage_site",
        "signal_peptide_cleavage_probability",
    )
    for r in results:
        for col in _EDGE_PROP_COLS:
            if r.get(col) is None:
                r.pop(col, None)
```

- [ ] **Step 8.5: Update `gene_ontology_terms` post-process**

Apply the same strip block in `gene_ontology_terms` results-iteration. Find the analogous results-processing block (where rows are flattened across ontologies) and append the same strip loop. Use the same `_EDGE_PROP_COLS` constant — extract to module scope so both functions share it:

At the top of `multiomics_explorer/api/functions.py` (after imports, before the first function), add:

```python
_EDGE_PROP_COLS: tuple[str, ...] = (
    "localization_score",
    "signal_peptide_probability",
    "signal_peptide_cleavage_site",
    "signal_peptide_cleavage_probability",
)
```

Then in BOTH `genes_by_ontology` and `gene_ontology_terms`, after the existing strip blocks for sparse columns, append:

```python
    for r in results:
        for col in _EDGE_PROP_COLS:
            if r.get(col) is None:
                r.pop(col, None)
```

(In `genes_by_ontology`, remove the inline `_EDGE_PROP_COLS` literal from Step 8.4 since we hoisted it.)

- [ ] **Step 8.6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_functions.py::TestGenesByOntologyEdgePropStripping -v`

Expected: 2 PASS.

Run broader api/ tests to catch regressions:

Run: `uv run pytest tests/unit/test_api_functions.py -k "ontology" -v`

Expected: ALL pass. If any existing test asserts the absence of edge-prop columns in pre-existing-ontology rows, those should continue passing (the strip removes the nulls).

- [ ] **Step 8.7: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "feat(api): strip sparse edge-prop nulls on non-owner ontology rows"
```

---

## Task 9: MCP wrappers — Literal bumps + Pydantic field additions

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` (lines 2125-2128, 2183-2203, 2265-2269, 2374-2384, 2430-2432, 5534-5536, 5629-5632, 5774-5777)
- Test: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 9.1: Write failing tests for Literal acceptance + Pydantic fields**

Append to `tests/unit/test_tool_wrappers.py` (immediately after the `TestOntologyLiteralAcceptsTcdbCazy` class at line 6328):

```python
class TestOntologyLiteralAcceptsPsortbSignalp:
    """The closed Literal[...] enums on the 5 ontology wrappers must accept
    'subcellular_localization' and 'signal_peptide_type'. Mirrors
    TestOntologyLiteralAcceptsTcdbCazy."""

    @staticmethod
    def _ontology_hint_str(tool_fns, tool_name: str) -> str:
        import typing
        fn = tool_fns[tool_name]
        hints = typing.get_type_hints(fn, include_extras=True)
        ontology_hint = hints.get("ontology")
        assert ontology_hint is not None, (
            f"ontology parameter not found in type hints for {tool_name}"
        )
        return str(ontology_hint)

    def test_genes_by_ontology_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "genes_by_ontology")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_gene_ontology_terms_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "gene_ontology_terms")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_ontology_landscape_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "ontology_landscape")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_pathway_enrichment_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "pathway_enrichment")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_cluster_enrichment_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "cluster_enrichment")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_search_ontology_description_mentions_new_keys(self, tool_fns):
        import typing
        fn = tool_fns["search_ontology"]
        hints = typing.get_type_hints(fn, include_extras=True)
        ontology_hint = hints.get("ontology")
        assert ontology_hint is not None
        descriptions = [
            getattr(meta, "description", None) for meta in
            getattr(ontology_hint, "__metadata__", ())
        ]
        joined = " ".join(d for d in descriptions if d)
        assert "subcellular_localization" in joined
        assert "signal_peptide_type" in joined


class TestEdgePropFieldsOnRowModels:
    """The GenesByOntologyResult and OntologyTermRow Pydantic classes
    must carry the 4 optional edge-prop fields (default=None, sparse)."""

    def test_genes_by_ontology_result_has_edge_prop_fields(self):
        from multiomics_explorer.mcp_server.tools import register_tools
        # GenesByOntologyResult is nested inside register_tools; build it
        # via the same fixture path used elsewhere in the file.
        import inspect
        src = inspect.getsource(register_tools)
        assert "localization_score:" in src
        assert "signal_peptide_probability:" in src
        assert "signal_peptide_cleavage_site:" in src
        assert "signal_peptide_cleavage_probability:" in src
        # Sanity: they must be on the right row class (GenesByOntologyResult)
        # — locate by searching for the class name's region.
        idx = src.index("class GenesByOntologyResult(BaseModel):")
        end_idx = src.index("class OntologyCategoryBreakdown(BaseModel):", idx)
        section = src[idx:end_idx]
        assert "localization_score:" in section, (
            "localization_score must be a field on GenesByOntologyResult"
        )
        assert "signal_peptide_probability:" in section

    def test_ontology_term_row_has_edge_prop_fields(self):
        from multiomics_explorer.mcp_server.tools import register_tools
        import inspect
        src = inspect.getsource(register_tools)
        idx = src.index("class OntologyTermRow(BaseModel):")
        end_idx = src.index("class OntologyTypeBreakdown(BaseModel):", idx)
        section = src[idx:end_idx]
        assert "localization_score:" in section
        assert "signal_peptide_probability:" in section
        assert "signal_peptide_cleavage_site:" in section
        assert "signal_peptide_cleavage_probability:" in section


class TestExpectedToolsUnchangedForPsortbSignalp:
    """Adding subcellular_localization/signal_peptide_type as ontology
    dimensions does NOT add new tool entries."""

    def test_no_new_tools_added(self, tool_fns):
        assert "subcellular_localization" not in tool_fns
        assert "signal_peptide_type" not in tool_fns
        assert "psortb" not in tool_fns
        assert "signalp" not in tool_fns

    def test_expected_tools_size_unchanged_at_39(self):
        # No new tool — only ontology surface refresh.
        assert len(EXPECTED_TOOLS) == 39, (
            f"EXPECTED_TOOLS unexpectedly has {len(EXPECTED_TOOLS)} entries; "
            "psortb/signalp adds NO new tools (Mode-B ontology surface refresh)."
        )
```

- [ ] **Step 9.2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_tool_wrappers.py -k "PsortbSignalp or EdgePropFieldsOnRowModels" -v`

Expected: 10 FAIL.

- [ ] **Step 9.3: Bump 5 Literal enums**

Edit `multiomics_explorer/mcp_server/tools.py` at the 5 sites:

**Site 1 — `genes_by_ontology` (line 2265-2269):**

```python
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
            "tcdb", "cazy",
            "subcellular_localization", "signal_peptide_type",
        ], Field(
            description="Ontology for these term_ids / this level.",
        )],
```

**Site 2 — `gene_ontology_terms` (line 2429-2433):**

```python
        ontology: Annotated[
            Literal["go_bp", "go_mf", "go_cc", "kegg", "ec",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
                    "tcdb", "cazy",
                    "subcellular_localization", "signal_peptide_type"] | None,
            Field(description="Filter to one ontology. None returns all."),
        ] = None,
```

**Site 3 — `ontology_landscape` (line 5533-5537):**

```python
        ontology: Annotated[
            Literal["go_bp", "go_mf", "go_cc", "ec", "kegg",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
                    "tcdb", "cazy",
                    "subcellular_localization", "signal_peptide_type"] | None,
            Field(description="If None, surveys all ontologies."),
        ] = None,
```

**Site 4 — `pathway_enrichment` (line 5629-5633):**

```python
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
            "tcdb", "cazy",
            "subcellular_localization", "signal_peptide_type",
        ], Field(
            description="Ontology for pathway definitions. Run ontology_landscape first to rank by relevance.",
        )],
```

**Site 5 — `cluster_enrichment` (line 5774-5778):**

```python
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
            "tcdb", "cazy",
            "subcellular_localization", "signal_peptide_type",
        ], Field(description="Ontology for pathway definitions. Run ontology_landscape first.")],
```

- [ ] **Step 9.4: Update `search_ontology` description**

Edit lines 2125-2128 of `multiomics_explorer/mcp_server/tools.py`:

```python
        ontology: Annotated[str, Field(
            description="Ontology to search: 'go_bp', 'go_mf', 'go_cc', "
            "'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', "
            "'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type'.",
        )],
```

- [ ] **Step 9.5: Add 4 optional fields to `GenesByOntologyResult`**

Edit `multiomics_explorer/mcp_server/tools.py` around line 2183-2203. After the existing `tree_code` field (line 2196), before the `# verbose only` comment, add:

```python
        # Edge-prop columns (sparse — only set when matching ontology)
        localization_score: float | None = Field(default=None,
            description="PSORTb confidence score (sparse: only set when "
                        "ontology='subcellular_localization'). Range 7.5–10.0.")
        signal_peptide_probability: float | None = Field(default=None,
            description="SignalP winning-class probability (sparse: only set "
                        "when ontology='signal_peptide_type'). Range 0–1.")
        signal_peptide_cleavage_site: int | None = Field(default=None,
            description="SignalP-predicted cleavage residue position (sparse: "
                        "only set when ontology='signal_peptide_type'; absent "
                        "when SignalP reports no cleavage site).")
        signal_peptide_cleavage_probability: float | None = Field(default=None,
            description="SignalP cleavage-site probability (sparse: only set "
                        "when ontology='signal_peptide_type' and cleavage_site "
                        "present).")
```

- [ ] **Step 9.6: Add 4 optional fields to `OntologyTermRow`**

Edit `multiomics_explorer/mcp_server/tools.py` around line 2374-2384. After the existing `tree_code` field (line 2382), before the `# verbose-only` comment, add the same 4 fields (verbatim from Step 9.5).

- [ ] **Step 9.7: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tool_wrappers.py -k "PsortbSignalp or EdgePropFieldsOnRowModels" -v`

Expected: 10 PASS.

Also run the broader wrapper suite to catch regressions:

Run: `uv run pytest tests/unit/test_tool_wrappers.py -v`

Expected: ALL pass. The pre-existing `TestExpectedToolsUnchangedForTcdbCazy::test_expected_tools_size_unchanged` should still pass at 39.

- [ ] **Step 9.8: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat(mcp): bump ontology Literals + add edge-prop row fields for psortb/signalp"
```

---

## Task 10: YAML inputs + about-content regeneration + CLAUDE.md

**Files:**
- Modify: `multiomics_explorer/inputs/tools/search_ontology.yaml`
- Modify: `multiomics_explorer/inputs/tools/ontology_landscape.yaml`
- Modify: `multiomics_explorer/inputs/tools/genes_by_ontology.yaml`
- Modify: `multiomics_explorer/inputs/tools/gene_ontology_terms.yaml`
- Run: `scripts/build_about_content.py`
- Modify: `CLAUDE.md` (search_ontology row + genes_by_ontology row)

- [ ] **Step 10.1: Add examples to `search_ontology.yaml`**

Edit `multiomics_explorer/inputs/tools/search_ontology.yaml`. Append two examples after the existing TCDB example (around line 60-65):

```yaml
  - title: Find PSORTb subcellular localizations
    call: search_ontology(search_text="outer", ontology="subcellular_localization")
    response: |
      {
        "total_entries": 5,
        "total_matching": 1,
        "score_max": 2.42,
        "score_median": 2.42,
        "returned": 1,
        "truncated": false,
        "offset": 0,
        "results": [
          {"id": "psortb_OuterMembrane", "name": "Outer membrane",
           "score": 2.42, "level": 0}
        ]
      }

  - title: Find SignalP lipoprotein signal-peptide types
    call: search_ontology(search_text="lipo", ontology="signal_peptide_type")
    response: |
      {
        "total_entries": 5,
        "total_matching": 2,
        "score_max": 3.1,
        "score_median": 2.6,
        "returned": 2,
        "truncated": false,
        "offset": 0,
        "results": [
          {"id": "signalp_LIPO", "name": "Lipoprotein signal peptide (Sec/SPII)",
           "score": 3.1, "level": 0},
          {"id": "signalp_TATLIPO", "name": "TAT lipoprotein signal peptide (Tat/SPII)",
           "score": 2.6, "level": 0}
        ]
      }
```

Locate the `mistakes:` block (if present in the yaml) and append:

```yaml
  - "PSORTb and SignalP ontologies are **flat** (5 nodes each, single `level=0`).
     Don't pass `level=1` or higher — the search returns nothing because no
     terms exist at those levels."
  - "PSORTb / SignalP are **structural** ontologies (where a gene's product is /
     how it's handled). Use them for localization / secretion questions, not
     for functional-annotation `genes_by_function`-style proxies."
```

- [ ] **Step 10.2: Add example to `ontology_landscape.yaml`**

Edit `multiomics_explorer/inputs/tools/ontology_landscape.yaml`. Append one example showing the two new ontologies appearing in the `by_ontology` envelope at `level=0`. Locate an existing example with a multi-ontology fan-out response and add a new one with the psortb/signalp rows. (Specifically, after the cazy example block.) Example:

```yaml
  - title: PSORTb + SignalP appear at level=0
    call: ontology_landscape(organism="MED4")
    response: |
      {
        "by_ontology": [
          ...,
          {"ontology": "subcellular_localization", "level": 0, "level_kind": null,
           "n_terms_with_genes": 5, "min_g": 30, "max_g": 1100, ...},
          {"ontology": "signal_peptide_type", "level": 0, "level_kind": null,
           "n_terms_with_genes": 3, "min_g": 5, "max_g": 220, ...}
        ]
      }
```

(Counts are illustrative; the live values will be verified in Task 11.)

Append to the yaml's `mistakes:` block:

```yaml
  - "PSORTb / SignalP are flat (single `level=0`) — they contribute exactly one
     row to `by_ontology` per organism. If only 1-2 of the 5 nodes pass the
     default `min_gene_set_size=5` filter, the small N is expected (categories
     range from ~30 to ~50,000 genes genome-wide; per-organism it's much
     smaller)."
```

- [ ] **Step 10.3: Add examples to `genes_by_ontology.yaml`**

Edit `multiomics_explorer/inputs/tools/genes_by_ontology.yaml`. Append two examples (after the existing TCDB / CAZy examples):

```yaml
  - title: PSORTb outer-membrane proteins with confidence score
    call: genes_by_ontology(ontology="subcellular_localization", term_ids=["psortb_OuterMembrane"], organism="MED4")
    response: |
      {
        "ontology": "subcellular_localization",
        "organism_name": "MED4",
        "total_matching": 45,
        ...,
        "results": [
          {"locus_tag": "PMM0001", "gene_name": "...",
           "term_id": "psortb_OuterMembrane",
           "term_name": "Outer membrane", "level": 0,
           "is_informative": true,
           "localization_score": 9.93},
          ...
        ]
      }

  - title: SignalP lipoproteins with cleavage info
    call: genes_by_ontology(ontology="signal_peptide_type", term_ids=["signalp_LIPO"], organism="MED4")
    response: |
      {
        ...,
        "results": [
          {"locus_tag": "PMM0123",
           "term_id": "signalp_LIPO", "term_name": "Lipoprotein signal peptide (Sec/SPII)",
           "level": 0, "is_informative": true,
           "signal_peptide_probability": 0.97,
           "signal_peptide_cleavage_site": 22,
           "signal_peptide_cleavage_probability": 0.91}
        ]
      }
```

Append to the yaml's `mistakes:` block:

```yaml
  - "`localization_score` / `signal_peptide_probability` are **edge** properties —
     they appear in rows only when querying their owner ontology. Other ontology
     queries omit those columns entirely (sparse-null stripping at the api layer)."
  - "PSORTb and SignalP are 1:1 (≤1 edge per gene). Don't expect multiple rows
     per gene for the same ontology. Some genes will have **no** edge (no
     confident call); those genes are absent from the result set entirely."
```

Append to the yaml's `chaining:` block (if present):

```yaml
  - "From PSORTb-filtered genes → differential_expression_by_gene to ask: are
     outer-membrane proteins enriched in the up-regulated set?"
```

- [ ] **Step 10.4: Add example to `gene_ontology_terms.yaml`**

Edit `multiomics_explorer/inputs/tools/gene_ontology_terms.yaml`. Append:

```yaml
  - title: Per-gene SignalP call with cleavage info
    call: gene_ontology_terms(locus_tags=["PMM0001", "PMM0123"], ontology="signal_peptide_type", organism="MED4", mode="leaf")
    response: |
      {
        ...,
        "results": [
          {"locus_tag": "PMM0001", "term_id": "signalp_SP",
           "term_name": "Signal peptide (Sec/SPI)", "level": 0,
           "is_informative": true,
           "signal_peptide_probability": 0.93,
           "signal_peptide_cleavage_site": 25,
           "signal_peptide_cleavage_probability": 0.85},
          {"locus_tag": "PMM0123", "term_id": "signalp_PILIN",
           "term_name": "Pilin-like signal peptide (Sec/SPIII)", "level": 0,
           "is_informative": true,
           "signal_peptide_probability": 0.78}
        ]
      }
```

(PILIN row demonstrates the no-cleavage case — `cleavage_site` and
`cleavage_probability` absent from the row dict.)

- [ ] **Step 10.5: Regenerate skills tree**

Run: `uv run python scripts/build_about_content.py`

Expected output: a list of regenerated `*.md` files under
`multiomics_explorer/skills/multiomics-kg-guide/references/tools/`, including
`search_ontology.md`, `ontology_landscape.md`, `genes_by_ontology.md`, and
`gene_ontology_terms.md`. No errors.

- [ ] **Step 10.6: Update `CLAUDE.md` ontology-tool rows**

Edit `CLAUDE.md` — locate the `search_ontology` row in the tool table. Change the parenthetical list of supported ontologies from:

```
(GO, KEGG, EC, COG, Cyanorak, TIGR, Pfam, BRITE, TCDB, CAZy)
```

to:

```
(GO, KEGG, EC, COG, Cyanorak, TIGR, Pfam, BRITE, TCDB, CAZy, PSORTb subcellular localization, SignalP signal-peptide type)
```

Repeat for the `genes_by_ontology` row.

- [ ] **Step 10.7: Run about-content tests + about-content lint**

Run: `uv run pytest tests/unit/test_about_content.py tests/unit/test_analysis_about_content.py tests/unit/test_examples_about_content.py tests/unit/test_guide_about_content.py -v`

Expected: ALL pass.

- [ ] **Step 10.8: Commit**

```bash
git add multiomics_explorer/inputs/tools/*.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/ \
        CLAUDE.md
git commit -m "docs: surface psortb/signalp in 4 ontology tool yamls + CLAUDE.md"
```

---

## Task 11: Integration smoke tests against live KG

**Files:**
- Modify: `tests/integration/test_mcp_tools.py` (append new test classes)

- [ ] **Step 11.1: Write integration tests for the 4 ontology tools**

Append to `tests/integration/test_mcp_tools.py` (find an existing `@pytest.mark.kg` integration class for the ontology tools to mirror the structure):

```python
@pytest.mark.kg
class TestOntologyToolsPsortbSignalpLive:
    """Smoke tests for psortb/signalp surfacing against live KG.
    Asserts only:
      - non-empty results
      - edge-prop columns populated on owner ontology
      - edge-prop columns absent on non-owner ontology
    NOT biological correctness (the KG-side is the source of truth for that)."""

    ORGANISM = "Prochlorococcus marinus MED4"

    def test_search_ontology_psortb(self, mcp_tools):
        result = mcp_tools.search_ontology(
            search_text="outer", ontology="subcellular_localization",
        )
        assert result["total_matching"] >= 1
        assert any(r["id"] == "psortb_OuterMembrane" for r in result["results"])

    def test_search_ontology_signalp(self, mcp_tools):
        result = mcp_tools.search_ontology(
            search_text="lipo", ontology="signal_peptide_type",
        )
        assert result["total_matching"] >= 1
        result_ids = {r["id"] for r in result["results"]}
        assert "signalp_LIPO" in result_ids or "signalp_TATLIPO" in result_ids

    def test_genes_by_ontology_psortb_surfaces_score(self, mcp_tools):
        result = mcp_tools.genes_by_ontology(
            ontology="subcellular_localization",
            term_ids=["psortb_OuterMembrane"],
            organism=self.ORGANISM,
        )
        assert result["total_matching"] > 0
        rows = result["results"]
        assert rows, "Expected at least one PMM* gene with OuterMembrane call"
        for row in rows:
            # Owner column populated, range [7.5, 10.0]
            assert "localization_score" in row, row
            assert 7.5 <= row["localization_score"] <= 10.0
            # Non-owner columns absent (stripped sparse-null)
            assert "signal_peptide_probability" not in row
            assert "signal_peptide_cleavage_site" not in row
            assert "signal_peptide_cleavage_probability" not in row

    def test_genes_by_ontology_signalp_surfaces_probability(self, mcp_tools):
        result = mcp_tools.genes_by_ontology(
            ontology="signal_peptide_type",
            term_ids=["signalp_LIPO"],
            organism=self.ORGANISM,
        )
        rows = result["results"]
        if rows:
            for row in rows:
                assert "signal_peptide_probability" in row
                assert 0.0 <= row["signal_peptide_probability"] <= 1.0
                # cleavage_site may or may not be present (depends on the gene);
                # both states must not crash
                assert "localization_score" not in row

    def test_genes_by_ontology_pfam_strips_edge_prop_columns(self, mcp_tools):
        """Pre-existing ontology should NOT have the 4 edge-prop columns
        in its rows."""
        result = mcp_tools.genes_by_ontology(
            ontology="pfam",
            level=1,
            organism=self.ORGANISM,
            min_gene_set_size=5,
            limit=5,
        )
        for row in result["results"]:
            assert "localization_score" not in row
            assert "signal_peptide_probability" not in row
            assert "signal_peptide_cleavage_site" not in row
            assert "signal_peptide_cleavage_probability" not in row

    def test_ontology_landscape_includes_new_ontologies(self, mcp_tools):
        """All-ontologies fan-out includes the two new flat ontologies."""
        result = mcp_tools.ontology_landscape(organism=self.ORGANISM)
        ontologies_seen = {row["ontology"] for row in result["by_ontology"]}
        assert "subcellular_localization" in ontologies_seen
        assert "signal_peptide_type" in ontologies_seen
        # All-flat → level=0 only
        for row in result["by_ontology"]:
            if row["ontology"] in ("subcellular_localization", "signal_peptide_type"):
                assert row["level"] == 0

    def test_gene_ontology_terms_signalp_handles_cleavage_absence(self, mcp_tools):
        """For a SignalP-PILIN gene (typically no cleavage site), the row
        emits null cleavage fields cleanly — both states must not crash."""
        # Find a PILIN gene first via search
        sp_search = mcp_tools.genes_by_ontology(
            ontology="signal_peptide_type",
            term_ids=["signalp_PILIN"],
            organism=self.ORGANISM,
            limit=3,
        )
        if not sp_search["results"]:
            pytest.skip("No PILIN genes in MED4 — skip cleavage-absence test")
        pilin_lts = [r["locus_tag"] for r in sp_search["results"]][:2]
        result = mcp_tools.gene_ontology_terms(
            locus_tags=pilin_lts,
            ontology="signal_peptide_type",
            organism=self.ORGANISM,
            mode="leaf",
        )
        for row in result["results"]:
            assert row["term_id"] == "signalp_PILIN"
            assert "signal_peptide_probability" in row
            # cleavage_site / cleavage_probability absent (stripped null)
            # or present (rare); both fine
```

- [ ] **Step 11.2: Run integration tests**

Run: `uv run pytest tests/integration/test_mcp_tools.py::TestOntologyToolsPsortbSignalpLive -v -m kg`

Expected: 7 PASS. If a test fails because:
- "Live KG missing the new ontology": STOP — re-run pre-flight queries to confirm the KG state matches the spec.
- "Edge-prop column absent on owner row": Tasks 6/7 didn't land — investigate the matched cypher built by the query builder.
- "Edge-prop column present on non-owner row": Task 8 strip didn't run — investigate api/ layer.

- [ ] **Step 11.3: Commit**

```bash
git add tests/integration/test_mcp_tools.py
git commit -m "test: live-KG smoke tests for psortb/signalp ontology surface"
```

---

## Task 12: Regression fixture regeneration + guardrail audit

**Files:**
- Modify: `tests/regression/fixtures/**/*.json` (regenerated)
- Verify (do NOT modify by hand): regenerated fixtures contain only-additive changes

The regression suite snapshots full envelopes for canonical inputs. After Tasks 6, 7, and 8 land, ALL ontology-tool fixtures grow by the 4 new edge-prop columns (or shrink, post-strip — depending on the row's owner). All-ontologies-fan-out fixtures (`ontology_landscape`) grow by the 2 new ontology slots.

- [ ] **Step 12.1: Run regression before regenerating — capture the failures**

Run: `uv run pytest tests/regression/ -v 2>&1 | head -100`

Expected: many FAILURES across the 4 ontology tools' fixtures.

For each tool that fails, the failure mode should be **only** one of:
- "row has new column `localization_score` (or similar)" — expected.
- "by_ontology has new entries `subcellular_localization` / `signal_peptide_type`" — expected.

If you see a failure that's neither of these (e.g. an existing row's data has a different value), STOP — investigate before regenerating.

- [ ] **Step 12.2: Regenerate fixtures**

Run: `uv run pytest tests/regression/ --force-regen -v`

(If the regression suite uses a different regen mechanism — e.g. `regenerate.py` or an env var — substitute accordingly. Check the regression test file header for instructions.)

Expected: regenerates the fixture JSON files. Re-run without `--force-regen`:

Run: `uv run pytest tests/regression/ -v`

Expected: ALL pass.

- [ ] **Step 12.3: Audit the diff**

Run: `git diff tests/regression/fixtures/`

Sample at least one fixture from each of the 4 affected ontology tools (search_ontology, ontology_landscape, genes_by_ontology, gene_ontology_terms). Verify:
- For non-owner ontologies (e.g. existing TCDB / Pfam fixtures): rows do NOT gain edge-prop columns (strip works).
- For all-ontology fan-out (ontology_landscape): `by_ontology` array grew by 2 entries; **no existing entry was modified** (values unchanged for the 12 pre-existing ontologies).
- For genes_by_ontology and gene_ontology_terms fixtures keyed by a non-PSORTb-non-SignalP ontology: row count unchanged, row content unchanged.

If you find any row whose values changed beyond "added 4 null columns" or "added 2 new ontology entries," STOP — this is a regression, not an expected delta. Investigate.

- [ ] **Step 12.4: Commit**

```bash
git add tests/regression/fixtures/
git commit -m "test: regenerate ontology-tool regression fixtures for psortb/signalp"
```

---

## Task 13: Final verification

- [ ] **Step 13.1: Run the full unit suite**

Run: `uv run pytest tests/unit/ -v`

Expected: ALL pass.

- [ ] **Step 13.2: Run the full kg-marked suite**

Run: `uv run pytest -m kg -v`

Expected: ALL pass.

- [ ] **Step 13.3: Run the regression suite without --force-regen**

Run: `uv run pytest tests/regression/ -v`

Expected: ALL pass.

- [ ] **Step 13.4: Confirm `EXPECTED_TOOLS` count is still 39**

Run: `grep "EXPECTED_TOOLS" multiomics_explorer/mcp_server/tools.py | head -5`

Confirm the count is 39 (no new tools added). If it grew to 40+, a new tool was inadvertently registered — investigate.

- [ ] **Step 13.5: Quick spot-check the MCP server boots cleanly**

Run: `uv run multiomics-kg-mcp --help`

Expected: usage output without import errors.

(For a deeper smoke check, the user can manually re-attach the MCP server via `/mcp` and run `kg_schema()` followed by `genes_by_ontology(ontology="subcellular_localization", term_ids=["psortb_OuterMembrane"], organism="MED4")` — but that requires session restart and is outside the agent's scope.)

- [ ] **Step 13.6: Commit any incidental fixes**

```bash
git status
# If only fixtures + plan/spec changes are present, no further commit needed.
# If real code drift exists, investigate before committing.
```

---

## Notes for the implementer

1. **Tests-first discipline is load-bearing.** The rel-binding refactor (Tasks 3-7) touches code paths used by every ontology — fix RED first, never bypass the failing-test step.
2. **The regression-fixture guardrail (Task 12.3) is mandatory.** If you see a fixture diff that's NOT "added 4 null columns" or "added 2 new ontology slots," STOP and surface to the user. Silent rebaseline is forbidden.
3. **Restart the MCP server after Step 13.5** so the next user session sees the new tools (per `feedback_mcp_restart`).
4. **The `psortb` / `signalp` keys do NOT exist** anywhere in the explorer — only `subcellular_localization` and `signal_peptide_type` are the public keys. The `psortb_*` / `signalp_*` prefixes are KG node-ID prefixes (term IDs) and are passed verbatim through `term_ids`.
5. **The 2026-05-27 SignalP KG rebuild also added `Gene.subcellular_localization` and `Gene.signal_peptide_type` as routing strings** (per memory `project_seq_neighbors_shipped`). They're already on Gene nodes and surface via `gene_details`. This plan does NOT touch them — they're scope-creep-deferred to a separate routing-surface pass.
