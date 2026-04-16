# BRITE Ontology Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add KEGG BRITE functional hierarchies as the 10th ontology (`"brite"`) in the explorer, enabling all ontology tools to work with the 2,611 BriteCategory nodes across 12 BRITE trees.

**Architecture:** One `"brite"` key in `ONTOLOGY_CONFIG` with a new `bridge` field encoding the 2-hop gene→KeggTerm→BriteCategory path. `_hierarchy_walk` gains a bridge branch; all builders that use it inherit BRITE support. `_gene_ontology_terms_leaf_filter` skips bridge ontologies. No new tool parameters.

**Tech Stack:** Python, Neo4j (Cypher), FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-04-16-brite-ontology-integration-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `multiomics_explorer/kg/constants.py` | Modify | Add `"brite"` to `ALL_ONTOLOGIES` |
| `multiomics_explorer/kg/queries_lib.py` | Modify | ONTOLOGY_CONFIG entry, `_hierarchy_walk` bridge branch, leaf filter skip, `gene_ontology_terms` 2-hop |
| `multiomics_explorer/mcp_server/tools.py` | Modify | Add `"brite"` to 4 Literal type hints, update 1 description |
| `multiomics_explorer/config/schema_baseline.yaml` | Modify | Add BriteCategory node + 2 relationship types |
| `tests/unit/test_query_builders.py` | Modify | Tests for bridge branch, leaf filter, landscape, expcov, gene_ontology_terms |

---

### Task 1: ONTOLOGY_CONFIG + ALL_ONTOLOGIES

**Files:**
- Modify: `multiomics_explorer/kg/constants.py:5-8`
- Modify: `multiomics_explorer/kg/queries_lib.py:10-76`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing test for BRITE config existence**

In `tests/unit/test_query_builders.py`, add at the top of the file alongside existing imports area (after the existing test classes for `_hierarchy_walk`):

```python
class TestOntologyConfigBrite:
    def test_brite_in_ontology_config(self):
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        assert "brite" in ONTOLOGY_CONFIG
        cfg = ONTOLOGY_CONFIG["brite"]
        assert cfg["label"] == "BriteCategory"
        assert cfg["gene_rel"] == "Gene_has_kegg_ko"
        assert cfg["hierarchy_rels"] == ["Brite_category_is_a_brite_category"]
        assert cfg["fulltext_index"] == "briteCategoryFullText"
        assert cfg["bridge"] == {
            "node_label": "KeggTerm",
            "edge": "Kegg_term_in_brite_category",
        }

    def test_brite_in_all_ontologies(self):
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert "brite" in ALL_ONTOLOGIES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestOntologyConfigBrite -v`
Expected: FAIL — `"brite"` not in `ONTOLOGY_CONFIG` and not in `ALL_ONTOLOGIES`.

- [ ] **Step 3: Add BRITE to constants.py**

In `multiomics_explorer/kg/constants.py`, change `ALL_ONTOLOGIES`:

```python
ALL_ONTOLOGIES: list[str] = [
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam",
    "brite",
]
```

- [ ] **Step 4: Add BRITE to ONTOLOGY_CONFIG**

In `multiomics_explorer/kg/queries_lib.py`, after the `"pfam"` entry (line 75), add:

```python
    "brite": {
        "label": "BriteCategory",
        "gene_rel": "Gene_has_kegg_ko",
        "hierarchy_rels": ["Brite_category_is_a_brite_category"],
        "fulltext_index": "briteCategoryFullText",
        "bridge": {
            "node_label": "KeggTerm",
            "edge": "Kegg_term_in_brite_category",
        },
    },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestOntologyConfigBrite -v`
Expected: PASS

- [ ] **Step 6: Run full test suite to check for regressions**

Run: `pytest tests/unit/test_query_builders.py -v`
Expected: All existing tests PASS. The new config entry shouldn't break anything yet — `_hierarchy_walk` doesn't handle bridge yet, but no test calls it with `"brite"`.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/kg/constants.py multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add brite to ONTOLOGY_CONFIG and ALL_ONTOLOGIES"
```

---

### Task 2: `_hierarchy_walk` bridge branch

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:78-201`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for BRITE hierarchy walk**

Add to `TestHierarchyWalk` class in `tests/unit/test_query_builders.py`:

```python
    def test_brite_up_uses_bridge(self):
        frag = _hierarchy_walk("brite", direction="up")
        assert frag["leaf_label"] == "BriteCategory"
        assert frag["gene_rel"] == "Gene_has_kegg_ko"
        assert "Brite_category_is_a_brite_category" in frag["rel_union"]
        # 2-hop bind: Gene → KeggTerm → BriteCategory
        assert ":Gene_has_kegg_ko" in frag["bind_up"]
        assert ":KeggTerm" in frag["bind_up"]
        assert ":Kegg_term_in_brite_category" in frag["bind_up"]
        assert "(leaf:BriteCategory)" in frag["bind_up"]
        # Walk up within BriteCategory hierarchy
        assert "Brite_category_is_a_brite_category*0.." in frag["walk_up"]
        assert "(t:BriteCategory)" in frag["walk_up"]

    def test_brite_down_uses_bridge(self):
        frag = _hierarchy_walk("brite", direction="down")
        # Walk down: root → descendants within BriteCategory
        assert "(t:BriteCategory)<-[:Brite_category_is_a_brite_category*0..]-(leaf:BriteCategory)" in frag["walk_down"]

    def test_brite_bind_up_starts_with_standard_prefix(self):
        """bind_up must start with standard Gene prefix for expcov prefix-stripping."""
        frag = _hierarchy_walk("brite", direction="up")
        assert frag["bind_up"].startswith(
            "MATCH (g:Gene {organism_name: $org})"
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestHierarchyWalk::test_brite_up_uses_bridge tests/unit/test_query_builders.py::TestHierarchyWalk::test_brite_down_uses_bridge tests/unit/test_query_builders.py::TestHierarchyWalk::test_brite_bind_up_starts_with_standard_prefix -v`
Expected: FAIL — `_hierarchy_walk` with `"brite"` falls through to the single-label branch and emits wrong Cypher (using `Gene_has_kegg_ko` directly to `BriteCategory`).

- [ ] **Step 3: Add bridge branch to `_hierarchy_walk`**

In `multiomics_explorer/kg/queries_lib.py`, after the Pfam block (line 168) and before the flat-ontology check (line 170), add:

```python
    # --- Bridge ontologies (2-hop gene → intermediate → leaf) ---
    bridge = cfg.get("bridge")
    if bridge:
        bridge_edge = bridge["edge"]
        bridge_node = bridge["node_label"]
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[:{gene_rel}]->(ko:{bridge_node})"
            f"-[:{bridge_edge}]->(leaf:{leaf_label})"
        )
        walk_up = f"MATCH (leaf)-[:{rel_union}*0..]->(t:{leaf_label})"
        walk_down = (
            f"MATCH (t:{leaf_label})<-[:{rel_union}*0..]-(leaf:{leaf_label})"
        )
        return {
            "leaf_label": leaf_label,
            "gene_rel": gene_rel,
            "rel_union": rel_union,
            "bind_up": bind_up,
            "walk_up": walk_up,
            "walk_down": walk_down,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestHierarchyWalk -v`
Expected: All PASS, including new BRITE tests and existing tests for GO, Pfam, flat, KEGG.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add bridge branch in _hierarchy_walk for 2-hop BRITE traversal"
```

---

### Task 3: Leaf filter skip for bridge ontologies

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:1550-1575`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing test**

Add a new test class near the existing gene_ontology_terms tests:

```python
class TestGeneOntologyTermsLeafFilter:
    def test_bridge_ontology_skips_leaf_filter(self):
        from multiomics_explorer.kg.queries_lib import _gene_ontology_terms_leaf_filter, ONTOLOGY_CONFIG
        result = _gene_ontology_terms_leaf_filter(ONTOLOGY_CONFIG["brite"])
        assert result == "", "Bridge ontologies must skip leaf filter"

    def test_parent_label_ontology_still_skips(self):
        from multiomics_explorer.kg.queries_lib import _gene_ontology_terms_leaf_filter, ONTOLOGY_CONFIG
        result = _gene_ontology_terms_leaf_filter(ONTOLOGY_CONFIG["pfam"])
        assert result == ""

    def test_hierarchical_ontology_emits_filter(self):
        from multiomics_explorer.kg.queries_lib import _gene_ontology_terms_leaf_filter, ONTOLOGY_CONFIG
        result = _gene_ontology_terms_leaf_filter(ONTOLOGY_CONFIG["go_bp"])
        assert "NOT EXISTS" in result
```

- [ ] **Step 2: Run tests to verify the bridge test fails**

Run: `pytest tests/unit/test_query_builders.py::TestGeneOntologyTermsLeafFilter -v`
Expected: `test_bridge_ontology_skips_leaf_filter` FAIL (returns a WHERE clause instead of empty string). The other two should PASS.

- [ ] **Step 3: Add bridge skip to `_gene_ontology_terms_leaf_filter`**

In `multiomics_explorer/kg/queries_lib.py`, in `_gene_ontology_terms_leaf_filter` (around line 1565), after the `if cfg.get("parent_label"):` check, add:

```python
    if cfg.get("bridge"):
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestGeneOntologyTermsLeafFilter -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "fix: skip leaf filter for bridge ontologies (BRITE)"
```

---

### Task 4: `gene_ontology_terms` 2-hop builders

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:1578-1670`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_query_builders.py` (find the existing `TestBuildGeneOntologyTerms` or `TestBuildGeneOntologyTermsSummary` class and add these tests):

```python
class TestBuildGeneOntologyTermsBrite:
    def test_summary_uses_2hop_match(self):
        cypher, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="brite",
        )
        assert params == {"locus_tags": ["PMM0001"]}
        # Must have 2-hop: Gene → KeggTerm → BriteCategory
        assert ":Gene_has_kegg_ko" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert ":BriteCategory" in cypher
        # Must NOT have direct Gene→BriteCategory (which would be wrong)
        assert "Gene_has_kegg_ko]->(t:BriteCategory)" not in cypher

    def test_detail_uses_2hop_match(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite",
        )
        assert ":Gene_has_kegg_ko" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert ":BriteCategory" in cypher

    def test_detail_returns_expected_columns(self):
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite",
        )
        for col in ["locus_tag", "term_id", "term_name"]:
            assert col in cypher
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneOntologyTermsBrite -v`
Expected: FAIL — the builders use 1-hop `Gene_has_kegg_ko]->(t:BriteCategory)` which is wrong.

- [ ] **Step 3: Add bridge dispatch to `build_gene_ontology_terms_summary`**

In `multiomics_explorer/kg/queries_lib.py`, in `build_gene_ontology_terms_summary` (around line 1596–1601), replace the MATCH line construction. Change the section that builds the Cypher from:

```python
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        f"MATCH (g:Gene {{locus_tag: lt}})-[:{gene_rel}]->(t:{label})\n"
        f"{leaf_filter}"
```

to:

```python
    bridge = cfg.get("bridge")
    if bridge:
        match_line = (
            f"MATCH (g:Gene {{locus_tag: lt}})"
            f"-[:{gene_rel}]->(:{bridge['node_label']})"
            f"-[:{bridge['edge']}]->(t:{label})\n"
        )
    else:
        match_line = (
            f"MATCH (g:Gene {{locus_tag: lt}})-[:{gene_rel}]->(t:{label})\n"
        )

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        f"{match_line}"
        f"{leaf_filter}"
```

- [ ] **Step 4: Add bridge dispatch to `build_gene_ontology_terms`**

Same pattern in `build_gene_ontology_terms` (around line 1661–1663). Change:

```python
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        f"MATCH (g:Gene {{locus_tag: lt}})-[:{gene_rel}]->(t:{label})\n"
        f"{leaf_filter}"
```

to:

```python
    bridge = cfg.get("bridge")
    if bridge:
        match_line = (
            f"MATCH (g:Gene {{locus_tag: lt}})"
            f"-[:{gene_rel}]->(:{bridge['node_label']})"
            f"-[:{bridge['edge']}]->(t:{label})\n"
        )
    else:
        match_line = (
            f"MATCH (g:Gene {{locus_tag: lt}})-[:{gene_rel}]->(t:{label})\n"
        )

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        f"{match_line}"
        f"{leaf_filter}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneOntologyTermsBrite -v`
Expected: All PASS.

- [ ] **Step 6: Run existing gene_ontology_terms tests for regressions**

Run: `pytest tests/unit/test_query_builders.py -k "gene_ontology_terms" -v`
Expected: All existing tests PASS.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add 2-hop bridge dispatch to gene_ontology_terms builders"
```

---

### Task 5: `ontology_landscape` + `expcov` BRITE tests

**Files:**
- Test: `tests/unit/test_query_builders.py`

These builders already use `_hierarchy_walk`, so BRITE should work automatically. This task verifies that.

- [ ] **Step 1: Write tests for landscape with BRITE**

Add to `TestBuildOntologyLandscape` class:

```python
    def test_brite_uses_2hop_bridge(self):
        cypher, _ = build_ontology_landscape(
            ontology="brite", organism_name="Prochlorococcus MED4",
        )
        # 2-hop bind
        assert ":Gene_has_kegg_ko" in cypher
        assert ":KeggTerm" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert "(leaf:BriteCategory)" in cypher
        # Hierarchy walk
        assert "Brite_category_is_a_brite_category*0.." in cypher
        assert "(t:BriteCategory)" in cypher
        # Two MATCH clauses (bind + walk)
        assert cypher.count("MATCH") == 2
```

- [ ] **Step 2: Write test for expcov with BRITE**

Add to `TestBuildOntologyExpcov` class:

```python
    def test_brite_uses_2hop_bridge(self):
        cypher, _ = build_ontology_expcov(
            ontology="brite",
            organism_name="Prochlorococcus MED4",
            experiment_ids=["e1"],
        )
        assert ":Gene_has_kegg_ko" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert "(leaf:BriteCategory)" in cypher
        assert "Brite_category_is_a_brite_category*0.." in cypher
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_query_builders.py::TestBuildOntologyLandscape::test_brite_uses_2hop_bridge tests/unit/test_query_builders.py::TestBuildOntologyExpcov::test_brite_uses_2hop_bridge -v`
Expected: PASS — these builders dispatch through `_hierarchy_walk` which already handles bridge.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_query_builders.py
git commit -m "test: verify ontology_landscape and expcov work with BRITE bridge"
```

---

### Task 6: MCP tool Literal type hints

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py:985-987,1099-1101,1229-1231,3424-3426,3492-3494`

- [ ] **Step 1: Update `search_ontology` ontology description**

In `multiomics_explorer/mcp_server/tools.py` at line 985–987, change:

```python
        ontology: Annotated[str, Field(
            description="Ontology to search: 'go_bp', 'go_mf', 'go_cc', "
            "'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam'.",
        )],
```

to:

```python
        ontology: Annotated[str, Field(
            description="Ontology to search: 'go_bp', 'go_mf', 'go_cc', "
            "'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite'.",
        )],
```

- [ ] **Step 2: Update `genes_by_ontology` Literal**

At line 1099–1101, change:

```python
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam",
        ], Field(
```

to:

```python
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
        ], Field(
```

- [ ] **Step 3: Update `gene_ontology_terms` Literal**

At line 1229–1231, change:

```python
            Literal["go_bp", "go_mf", "go_cc", "kegg", "ec",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam"] | None,
```

to:

```python
            Literal["go_bp", "go_mf", "go_cc", "kegg", "ec",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite"] | None,
```

- [ ] **Step 4: Update `ontology_landscape` Literal**

At line 3424–3426, change:

```python
            Literal["go_bp", "go_mf", "go_cc", "ec", "kegg",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam"] | None,
            Field(description="If None, surveys all 9 ontologies."),
```

to:

```python
            Literal["go_bp", "go_mf", "go_cc", "ec", "kegg",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite"] | None,
            Field(description="If None, surveys all 10 ontologies."),
```

- [ ] **Step 5: Update `pathway_enrichment` Literal**

At line 3492–3494, change:

```python
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam",
        ], Field(
```

to:

```python
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
        ], Field(
```

- [ ] **Step 6: Run unit tests**

Run: `pytest tests/unit/ -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "feat: add brite to ontology Literal type hints in MCP tools"
```

---

### Task 7: Schema baseline

**Files:**
- Regenerate: `multiomics_explorer/config/schema_baseline.yaml`

The schema baseline is captured from the live KG via `schema-snapshot`, not hand-edited.

- [ ] **Step 1: Regenerate schema baseline from live KG**

Run: `uv run multiomics-explorer schema-snapshot`

This introspects the live Neo4j instance and overwrites `multiomics_explorer/config/schema_baseline.yaml` with the current schema (including the new `BriteCategory` node, `Brite_category_is_a_brite_category` and `Kegg_term_in_brite_category` edges).

- [ ] **Step 2: Verify BriteCategory is captured**

Run: `grep -A 2 'BriteCategory' multiomics_explorer/config/schema_baseline.yaml | head -10`
Expected: `BriteCategory` node and both relationship types appear in the output.

- [ ] **Step 3: Run schema validation**

Run: `uv run multiomics-explorer schema-validate`
Expected: No drift (baseline matches live KG).

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/config/schema_baseline.yaml
git commit -m "chore: regenerate schema baseline (adds BriteCategory)"
```

---

### Task 8: Regression fixture regeneration

**Files:**
- Regenerate: fixtures used by ontology_landscape regression tests

- [ ] **Step 1: Identify affected fixtures**

Run: `grep -rn "brite\|ALL_ONTOLOGIES\|ontology_landscape.*fixture\|fixture.*ontology" tests/ --include="*.py" | head -20`

Check if `ontology_landscape` regression tests iterate `ALL_ONTOLOGIES`. If they do, adding `"brite"` means the fixture needs new rows.

- [ ] **Step 2: Run integration tests to find failures**

Run: `pytest -m kg -v -k "ontology_landscape or search_ontology or gene_ontology" 2>&1 | tail -40`

This reveals which fixtures need regeneration.

- [ ] **Step 3: Regenerate fixtures**

Follow the project's fixture regeneration pattern (check `tests/fixtures/` or `conftest.py` for `--regen` flags or similar). If fixtures are just expected-value dicts, update them with the actual output from step 2.

- [ ] **Step 4: Run integration tests again**

Run: `pytest -m kg -v -k "ontology_landscape or search_ontology or gene_ontology"`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: regenerate regression fixtures for BRITE ontology"
```

---

### Task 9: Integration smoke tests

**Files:**
- Test: `tests/integration/` (or run via `-m kg`)

These tests run against the live KG and verify end-to-end correctness.

- [ ] **Step 1: Test search_ontology with BRITE**

Run: `uv run python -c "
from multiomics_explorer.api.functions import search_ontology
r = search_ontology(ontology='brite', search_text='transporter*', limit=3)
print('total_matching:', r['total_matching'])
print('results:', r['results'][:2])
assert r['total_matching'] > 0
print('PASS')
"`
Expected: Prints matching BriteCategory terms.

- [ ] **Step 2: Test genes_by_ontology with BRITE**

Run: `uv run python -c "
from multiomics_explorer.api.functions import genes_by_ontology
r = genes_by_ontology(ontology='brite', organism='MED4', level=0, limit=3)
print('total_matching:', r['total_matching'])
print('sample:', r['results'][:2])
assert r['total_matching'] > 0
print('PASS')
"`
Expected: Returns genes grouped at BRITE level 0.

- [ ] **Step 3: Test gene_ontology_terms with BRITE**

Run: `uv run python -c "
from multiomics_explorer.api.functions import gene_ontology_terms
r = gene_ontology_terms(locus_tags=['PMM0001', 'PMM0003'], ontology='brite')
print('gene_count:', r.get('gene_count') or r.get('total_matching'))
print('sample:', r['results'][:3])
assert len(r['results']) > 0
print('PASS')
"`
Expected: Returns BRITE annotations for genes with KO edges.

- [ ] **Step 4: Test ontology_landscape includes BRITE**

Run: `uv run python -c "
from multiomics_explorer.api.functions import ontology_landscape
r = ontology_landscape(organism='MED4')
ontologies = {row['ontology_type'] for row in r['results']}
print('ontologies:', sorted(ontologies))
assert 'brite' in ontologies
print('BRITE levels:', [row for row in r['results'] if row['ontology_type'] == 'brite'])
print('PASS')
"`
Expected: `brite` appears in the landscape survey with rows for levels 0–3.

- [ ] **Step 5: Test pathway_enrichment with BRITE**

Run: `uv run python -c "
from multiomics_explorer.api.functions import list_experiments, pathway_enrichment
exps = list_experiments(organism='MED4')
eid = exps['results'][0]['experiment_id']
print('Using experiment:', eid)
r = pathway_enrichment(
    organism='MED4',
    experiment_ids=[eid],
    ontology='brite',
    level=1,
)
print('enriched terms:', len(r.get('results', [])))
print('PASS')
"`
Expected: Returns enrichment results using BRITE level 1 categories.

- [ ] **Step 6: Commit any integration test files if added**

```bash
git add tests/
git commit -m "test: BRITE integration smoke tests"
```

---

### Task 10: Skill docs and YAML inputs

**Files:**
- Modify: `multiomics_explorer/inputs/tools/ontology_landscape.yaml`
- Modify: `multiomics_explorer/inputs/tools/search_ontology.yaml`
- Modify: `multiomics_explorer/inputs/tools/genes_by_ontology.yaml`
- Modify: `multiomics_explorer/inputs/tools/gene_ontology_terms.yaml`
- Modify: `multiomics_explorer/inputs/tools/pathway_enrichment.yaml`

- [ ] **Step 1: Update ontology_landscape.yaml**

Add BRITE to the chaining section and add a mistake entry:

In the `mistakes:` section, add:
```yaml
  - "BRITE stats at each level mix all 12 trees together. For tree-specific analysis, use search_ontology to find term IDs in the target tree, then pass them to genes_by_ontology."
```

- [ ] **Step 2: Update search_ontology.yaml**

Add BRITE to the description of valid ontology values if listed there.

- [ ] **Step 3: Update genes_by_ontology.yaml**

Add BRITE to the description of valid ontology values if listed there.

- [ ] **Step 4: Update gene_ontology_terms.yaml**

Add BRITE to the description of valid ontology values if listed there.

- [ ] **Step 5: Update pathway_enrichment.yaml**

Add BRITE to valid ontology values.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/inputs/tools/
git commit -m "docs: add brite to tool YAML input files"
```

---

### Task 11: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update tool table**

In `CLAUDE.md`, update the `ontology_landscape` description from "all 9 ontologies" to "all 10 ontologies" and add a note that BRITE is available.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for 10th ontology (BRITE)"
```
