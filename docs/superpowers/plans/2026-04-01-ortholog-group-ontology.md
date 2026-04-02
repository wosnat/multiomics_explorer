# Ortholog Group Ontology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose CyanorakRole and CogFunctionalCategory annotations on ortholog groups through `search_homolog_groups` (filters + verbose columns + summary) and `gene_homologs` (verbose columns + summary).

**Architecture:** Enhance the shared `_gene_homologs_og_where` helper in queries_lib.py to accept `cyanorak_roles`/`cog_categories` list filters. Add OPTIONAL MATCH + collect patterns for verbose output and top-5 summary breakdowns. Propagate through API and MCP layers.

**Tech Stack:** Neo4j Cypher (EXISTS subqueries, OPTIONAL MATCH, apoc.coll.frequencies), Pydantic models, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `multiomics_explorer/kg/queries_lib.py` | Modify (lines 349-473, 1661-1756) | Add filter conditions to `_gene_homologs_og_where`, verbose ontology columns and summary breakdowns to 4 builders |
| `multiomics_explorer/api/functions.py` | Modify (lines 390-487, 888-1001) | Pass new params, reshape new summary fields |
| `multiomics_explorer/mcp_server/tools.py` | Modify (lines 520-635, 1686-1808) | New Pydantic models, new tool params, wire to API |
| `multiomics_explorer/inputs/tools/search_homolog_groups.yaml` | Modify | Add verbose_fields, update examples |
| `multiomics_explorer/inputs/tools/gene_homologs.yaml` | Modify | Add verbose_fields |
| `tests/unit/test_query_builders.py` | Modify (lines 392-578, 1903-2014) | Tests for new filter conditions and verbose columns |
| `tests/unit/test_api_functions.py` | Modify (lines 530-680, 2136-2244) | Tests for param passthrough and summary reshaping |
| `tests/unit/test_tool_wrappers.py` | Modify (lines 812-968, 2354-2484) | Tests for Pydantic models and param forwarding |
| `tests/integration/test_cyver_queries.py` | Modify (lines 187-205) | Add builder variants with new params |
| `tests/integration/test_api_contract.py` | Modify (lines 142-163, 598-638) | Add contract tests for new keys |

---

### Task 1: Query builders — `_gene_homologs_og_where` filter conditions

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:349-367`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for new filter params**

Add to `tests/unit/test_query_builders.py` — new tests in `TestBuildGeneHomologs` and `TestBuildSearchHomologGroups`:

```python
# In TestBuildGeneHomologs (after line ~522):

def test_cyanorak_roles_filter(self):
    cypher, params = build_gene_homologs(
        locus_tags=["PMM0845"], cyanorak_roles=["cyanorak.role:G.3"])
    assert "Og_has_cyanorak_role" in cypher
    assert "CyanorakRole" in cypher
    assert "$cyanorak_roles" in cypher
    assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]

def test_cog_categories_filter(self):
    cypher, params = build_gene_homologs(
        locus_tags=["PMM0845"], cog_categories=["cog.category:J"])
    assert "Og_in_cog_category" in cypher
    assert "CogFunctionalCategory" in cypher
    assert "$cog_categories" in cypher
    assert params["cog_categories"] == ["cog.category:J"]

def test_both_ontology_filters(self):
    cypher, params = build_gene_homologs(
        locus_tags=["PMM0845"],
        cyanorak_roles=["cyanorak.role:G.3"],
        cog_categories=["cog.category:J"],
    )
    assert "Og_has_cyanorak_role" in cypher
    assert "Og_in_cog_category" in cypher
    assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]
    assert params["cog_categories"] == ["cog.category:J"]

def test_ontology_filter_none_no_clause(self):
    cypher, params = build_gene_homologs(locus_tags=["PMM0845"])
    assert "Og_has_cyanorak_role" not in cypher
    assert "Og_in_cog_category" not in cypher
    assert "cyanorak_roles" not in params
    assert "cog_categories" not in params
```

Add matching tests in `TestBuildSearchHomologGroups`:

```python
def test_cyanorak_roles_filter(self):
    cypher, params = build_search_homolog_groups(
        search_text="test", cyanorak_roles=["cyanorak.role:G.3"])
    assert "Og_has_cyanorak_role" in cypher
    assert "$cyanorak_roles" in cypher
    assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]

def test_cog_categories_filter(self):
    cypher, params = build_search_homolog_groups(
        search_text="test", cog_categories=["cog.category:J"])
    assert "Og_in_cog_category" in cypher
    assert "$cog_categories" in cypher
    assert params["cog_categories"] == ["cog.category:J"]

def test_ontology_filter_none_no_clause(self):
    cypher, params = build_search_homolog_groups(search_text="test")
    assert "Og_has_cyanorak_role" not in cypher
    assert "Og_in_cog_category" not in cypher
```

Add matching tests in `TestBuildGeneHomologsSummary` and `TestBuildSearchHomologGroupsSummary`:

```python
# In TestBuildGeneHomologsSummary:
def test_cyanorak_roles_filter_forwarded(self):
    cypher, params = build_gene_homologs_summary(
        locus_tags=["x"], cyanorak_roles=["cyanorak.role:G.3"])
    assert "Og_has_cyanorak_role" in cypher
    assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]

def test_cog_categories_filter_forwarded(self):
    cypher, params = build_gene_homologs_summary(
        locus_tags=["x"], cog_categories=["cog.category:J"])
    assert "Og_in_cog_category" in cypher
    assert params["cog_categories"] == ["cog.category:J"]

# In TestBuildSearchHomologGroupsSummary:
def test_cyanorak_roles_filter_forwarded(self):
    cypher, params = build_search_homolog_groups_summary(
        search_text="test", cyanorak_roles=["cyanorak.role:G.3"])
    assert "Og_has_cyanorak_role" in cypher
    assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]

def test_cog_categories_filter_forwarded(self):
    cypher, params = build_search_homolog_groups_summary(
        search_text="test", cog_categories=["cog.category:J"])
    assert "Og_in_cog_category" in cypher
    assert params["cog_categories"] == ["cog.category:J"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneHomologs::test_cyanorak_roles_filter tests/unit/test_query_builders.py::TestBuildSearchHomologGroups::test_cyanorak_roles_filter -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'cyanorak_roles'`

- [ ] **Step 3: Implement filter conditions in `_gene_homologs_og_where`**

In `multiomics_explorer/kg/queries_lib.py:349-367`, add `cyanorak_roles` and `cog_categories` parameters:

```python
def _gene_homologs_og_where(
    *,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build OG filter conditions + params shared by gene_homologs builders."""
    conditions: list[str] = []
    params: dict = {}
    if source is not None:
        conditions.append("og.source = $source")
        params["source"] = source
    if taxonomic_level is not None:
        conditions.append("og.taxonomic_level = $level")
        params["level"] = taxonomic_level
    if max_specificity_rank is not None:
        conditions.append("og.specificity_rank <= $max_rank")
        params["max_rank"] = max_specificity_rank
    if cyanorak_roles is not None:
        conditions.append(
            "EXISTS { (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)"
            " WHERE cr.id IN $cyanorak_roles }"
        )
        params["cyanorak_roles"] = cyanorak_roles
    if cog_categories is not None:
        conditions.append(
            "EXISTS { (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)"
            " WHERE cc.id IN $cog_categories }"
        )
        params["cog_categories"] = cog_categories
    return conditions, params
```

Then update all callers of `_gene_homologs_og_where` to accept and forward the new params. Each builder function needs `cyanorak_roles` and `cog_categories` in its signature and must pass them to `_gene_homologs_og_where`:

**`build_gene_homologs_summary` (line 370):** Add params to signature and to the `_gene_homologs_og_where` call:
```python
def build_gene_homologs_summary(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
) -> tuple[str, dict]:
```
And in the body:
```python
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles, cog_categories=cog_categories,
    )
```

**`build_gene_homologs` (line 414):** Same pattern — add to signature and forward:
```python
def build_gene_homologs(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
```

**`build_search_homolog_groups_summary` (line 1661):** Same pattern.

**`build_search_homolog_groups` (line 1698):** Same pattern.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneHomologs tests/unit/test_query_builders.py::TestBuildGeneHomologsSummary tests/unit/test_query_builders.py::TestBuildSearchHomologGroups tests/unit/test_query_builders.py::TestBuildSearchHomologGroupsSummary -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add cyanorak_roles/cog_categories filters to OG query builders"
```

---

### Task 2: Query builders — verbose ontology columns

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:414-473` (`build_gene_homologs`), `multiomics_explorer/kg/queries_lib.py:1698-1756` (`build_search_homolog_groups`)
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for verbose ontology columns**

Add to `TestBuildGeneHomologs`:

```python
def test_verbose_includes_ontology_columns(self):
    cypher, _ = build_gene_homologs(locus_tags=["PMM0845"], verbose=True)
    assert "cyanorak_roles" in cypher
    assert "cog_categories" in cypher
    assert "Og_has_cyanorak_role" in cypher
    assert "Og_in_cog_category" in cypher
    assert "OPTIONAL MATCH" in cypher

def test_verbose_false_excludes_ontology_columns(self):
    cypher, _ = build_gene_homologs(locus_tags=["PMM0845"], verbose=False)
    assert "cyanorak_roles" not in cypher
    assert "cog_categories" not in cypher
```

Add to `TestBuildSearchHomologGroups`:

```python
def test_verbose_includes_ontology_columns(self):
    cypher, _ = build_search_homolog_groups(search_text="test", verbose=True)
    assert "cyanorak_roles" in cypher
    assert "cog_categories" in cypher
    assert "Og_has_cyanorak_role" in cypher
    assert "Og_in_cog_category" in cypher

def test_verbose_false_excludes_ontology_columns(self):
    cypher, _ = build_search_homolog_groups(search_text="test", verbose=False)
    assert "cyanorak_roles" not in cypher
    assert "cog_categories" not in cypher
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneHomologs::test_verbose_includes_ontology_columns tests/unit/test_query_builders.py::TestBuildSearchHomologGroups::test_verbose_includes_ontology_columns -v`
Expected: FAIL — `cyanorak_roles` not in cypher

- [ ] **Step 3: Add OPTIONAL MATCH + collect for verbose ontology in `build_gene_homologs`**

In `multiomics_explorer/kg/queries_lib.py`, modify `build_gene_homologs` (line 414). The current query is a simple UNWIND + MATCH + RETURN. For verbose mode, add OPTIONAL MATCH lines and collect the ontology terms. The key change is to insert OPTIONAL MATCH lines and wrap in a WITH clause before RETURN:

Replace the current Cypher construction (lines 461-472) with:

```python
    if verbose:
        cypher = (
            "UNWIND $locus_tags AS lt\n"
            "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
            f"{where_block}"
            "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
            "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
            "WITH g, og,\n"
            "     [x IN collect(DISTINCT {id: cr.id, name: cr.name}) WHERE x.id IS NOT NULL] AS cyanorak_roles,\n"
            "     [x IN collect(DISTINCT {id: cc.id, name: cc.name}) WHERE x.id IS NOT NULL] AS cog_categories\n"
            "RETURN g.locus_tag AS locus_tag, g.organism_name AS organism_name,\n"
            "       og.id AS group_id,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.taxonomic_level AS taxonomic_level, og.source AS source,\n"
            "       og.specificity_rank AS specificity_rank,\n"
            "       og.member_count AS member_count,\n"
            "       og.organism_count AS organism_count,\n"
            "       og.genera AS genera,\n"
            "       og.has_cross_genus_members AS has_cross_genus_members,\n"
            "       og.description AS description,\n"
            "       og.functional_description AS functional_description,\n"
            "       cyanorak_roles, cog_categories\n"
            f"ORDER BY g.locus_tag, og.specificity_rank, og.source{skip_clause}{limit_clause}"
        )
    else:
        cypher = (
            "UNWIND $locus_tags AS lt\n"
            "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
            f"{where_block}"
            "RETURN g.locus_tag AS locus_tag, g.organism_name AS organism_name,\n"
            "       og.id AS group_id,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.taxonomic_level AS taxonomic_level, og.source AS source,\n"
            f"       og.specificity_rank AS specificity_rank\n"
            f"ORDER BY g.locus_tag, og.specificity_rank, og.source{skip_clause}{limit_clause}"
        )
```

Note: This replaces the current `verbose_cols` string concatenation approach with an if/else because verbose mode now requires fundamentally different Cypher (OPTIONAL MATCH + WITH + collect), not just extra RETURN columns.

- [ ] **Step 4: Add OPTIONAL MATCH + collect for verbose ontology in `build_search_homolog_groups`**

Same pattern for `build_search_homolog_groups` (line 1698). Replace the current Cypher construction with an if/else:

```python
    if verbose:
        cypher = (
            "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
            "YIELD node AS og, score\n"
            f"{where_block}"
            "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
            "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
            "WITH og, score,\n"
            "     [x IN collect(DISTINCT {id: cr.id, name: cr.name}) WHERE x.id IS NOT NULL] AS cyanorak_roles,\n"
            "     [x IN collect(DISTINCT {id: cc.id, name: cc.name}) WHERE x.id IS NOT NULL] AS cog_categories\n"
            "RETURN og.id AS group_id, og.name AS group_name,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.source AS source, og.taxonomic_level AS taxonomic_level,\n"
            "       og.specificity_rank AS specificity_rank,\n"
            "       og.member_count AS member_count, og.organism_count AS organism_count,\n"
            "       score,\n"
            "       og.description AS description,\n"
            "       og.functional_description AS functional_description,\n"
            "       og.genera AS genera,\n"
            "       og.has_cross_genus_members AS has_cross_genus_members,\n"
            "       cyanorak_roles, cog_categories\n"
            f"ORDER BY score DESC, og.specificity_rank, og.source, og.id{skip_clause}{limit_clause}"
        )
    else:
        cypher = (
            "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
            "YIELD node AS og, score\n"
            f"{where_block}"
            "RETURN og.id AS group_id, og.name AS group_name,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.source AS source, og.taxonomic_level AS taxonomic_level,\n"
            "       og.specificity_rank AS specificity_rank,\n"
            "       og.member_count AS member_count, og.organism_count AS organism_count,\n"
            f"       score\n"
            f"ORDER BY score DESC, og.specificity_rank, og.source, og.id{skip_clause}{limit_clause}"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneHomologs tests/unit/test_query_builders.py::TestBuildSearchHomologGroups -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add verbose ontology columns to gene_homologs and search_homolog_groups builders"
```

---

### Task 3: Query builders — summary top-5 ontology breakdowns

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:370-411` (`build_gene_homologs_summary`), `multiomics_explorer/kg/queries_lib.py:1661-1695` (`build_search_homolog_groups_summary`)
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for summary ontology breakdowns**

Add to `TestBuildGeneHomologsSummary`:

```python
def test_summary_includes_top_ontology_breakdowns(self):
    cypher, _ = build_gene_homologs_summary(locus_tags=["PMM0845"])
    assert "top_cyanorak_roles" in cypher
    assert "top_cog_categories" in cypher
    assert "Og_has_cyanorak_role" in cypher
    assert "Og_in_cog_category" in cypher
```

Add to `TestBuildSearchHomologGroupsSummary`:

```python
def test_summary_includes_top_ontology_breakdowns(self):
    cypher, _ = build_search_homolog_groups_summary(search_text="test")
    assert "top_cyanorak_roles" in cypher
    assert "top_cog_categories" in cypher
    assert "Og_has_cyanorak_role" in cypher
    assert "Og_in_cog_category" in cypher
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneHomologsSummary::test_summary_includes_top_ontology_breakdowns tests/unit/test_query_builders.py::TestBuildSearchHomologGroupsSummary::test_summary_includes_top_ontology_breakdowns -v`
Expected: FAIL — `top_cyanorak_roles` not in cypher

- [ ] **Step 3: Add top-5 ontology breakdowns to `build_gene_homologs_summary`**

The current summary builder (lines 370-411) uses UNWIND + OPTIONAL MATCH + collect. We need to add OPTIONAL MATCH for the ontology edges and RETURN top-5 breakdowns. This requires a significant restructure of the Cypher.

Replace the cypher construction in `build_gene_homologs_summary` with:

```python
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (g)-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        f"{where_block}"
        "WITH lt, g, collect(og) AS groups\n"
        "WITH\n"
        "  collect(CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "  collect(CASE WHEN g IS NOT NULL AND size(groups) = 0 THEN lt END) AS ng_raw,\n"
        "  [row IN collect({org: CASE WHEN size(groups) > 0 THEN g.organism_name END,\n"
        "                    srcs: [x IN groups | x.source],\n"
        "                    og_ids: [x IN groups | x.id]})\n"
        "   WHERE row.org IS NOT NULL] AS matched\n"
        "UNWIND CASE WHEN size(matched) = 0 THEN [null] ELSE matched END AS m\n"
        "WITH nf_raw, ng_raw,\n"
        "     [x IN collect(m.org) WHERE x IS NOT NULL] AS orgs,\n"
        "     apoc.coll.flatten([x IN collect(m.srcs) WHERE x IS NOT NULL]) AS sources,\n"
        "     apoc.coll.toSet(apoc.coll.flatten(\n"
        "       [x IN collect(m.og_ids) WHERE x IS NOT NULL])) AS all_og_ids\n"
        "UNWIND CASE WHEN size(all_og_ids) = 0 THEN [null] ELSE all_og_ids END AS og_id\n"
        "OPTIONAL MATCH (og_node:OrthologGroup {id: og_id})-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
        "OPTIONAL MATCH (og_node)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
        "WITH nf_raw, ng_raw, orgs, sources,\n"
        "     collect(DISTINCT {id: cr.id, name: cr.name}) AS cr_pairs,\n"
        "     collect(DISTINCT {id: cc.id, name: cc.name}) AS cc_pairs\n"
        "WITH nf_raw, ng_raw, orgs, sources,\n"
        "     [p IN cr_pairs WHERE p.id IS NOT NULL | p.id + ' | ' + p.name] AS cr_items,\n"
        "     [p IN cc_pairs WHERE p.id IS NOT NULL | p.id + ' | ' + p.name] AS cc_items\n"
        "WITH *,\n"
        "     apoc.coll.frequencies(cr_items) AS cr_freq,\n"
        "     apoc.coll.frequencies(cc_items) AS cc_freq\n"
        "RETURN size(sources) AS total_matching,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(sources) AS by_source,\n"
        "       [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "       [x IN ng_raw WHERE x IS NOT NULL] AS no_groups,\n"
        "       [x IN cr_freq | {id: split(x.item, ' | ')[0],\n"
        "                         name: split(x.item, ' | ')[1],\n"
        "                         count: x.count}]\n"
        "         [0..5] AS top_cyanorak_roles,\n"
        "       [x IN cc_freq | {id: split(x.item, ' | ')[0],\n"
        "                         name: split(x.item, ' | ')[1],\n"
        "                         count: x.count}]\n"
        "         [0..5] AS top_cog_categories"
    )
```

**Important:** The `apoc.coll.frequencies` results are not guaranteed to be sorted by count. The top-5 may not be the 5 most frequent. This matches how `top_categories` works elsewhere in the codebase (using `[0..5]` slice without explicit sorting). If sorted order is needed, use UNWIND + ORDER BY + collect pattern instead (more complex). Keeping consistent with existing patterns for now.

- [ ] **Step 4: Add top-5 ontology breakdowns to `build_search_homolog_groups_summary`**

The current summary builder (lines 1661-1695) aggregates over fulltext results. Add ontology OPTIONAL MATCH:

Replace the cypher construction in `build_search_homolog_groups_summary` with:

```python
    cypher = (
        "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
        "YIELD node AS og, score\n"
        f"{where_block}"
        "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
        "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
        "WITH collect({src: og.source, lvl: og.taxonomic_level,\n"
        "              cr_id: cr.id, cr_name: cr.name,\n"
        "              cc_id: cc.id, cc_name: cc.name}) AS rows,\n"
        "     count(DISTINCT og) AS total_matching,\n"
        "     max(score) AS score_max,\n"
        "     percentileDisc(score, 0.5) AS score_median\n"
        "CALL { MATCH (all_og:OrthologGroup) RETURN count(all_og) AS total_entries }\n"
        "WITH *, [r IN rows | r.src] AS sources,\n"
        "        [r IN rows | r.lvl] AS levels,\n"
        "        [r IN rows WHERE r.cr_id IS NOT NULL | r.cr_id + ' | ' + r.cr_name] AS cr_items,\n"
        "        [r IN rows WHERE r.cc_id IS NOT NULL | r.cc_id + ' | ' + r.cc_name] AS cc_items\n"
        "WITH total_entries, total_matching, score_max, score_median,\n"
        "     apoc.coll.frequencies(sources) AS by_source,\n"
        "     apoc.coll.frequencies(levels) AS by_level,\n"
        "     apoc.coll.frequencies(cr_items) AS cr_freq,\n"
        "     apoc.coll.frequencies(cc_items) AS cc_freq\n"
        "RETURN total_entries, total_matching, score_max, score_median,\n"
        "       by_source, by_level,\n"
        "       [x IN cr_freq | {id: split(x.item, ' | ')[0],\n"
        "                         name: split(x.item, ' | ')[1],\n"
        "                         count: x.count}][0..5] AS top_cyanorak_roles,\n"
        "       [x IN cc_freq | {id: split(x.item, ' | ')[0],\n"
        "                         name: split(x.item, ' | ')[1],\n"
        "                         count: x.count}][0..5] AS top_cog_categories"
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneHomologsSummary tests/unit/test_query_builders.py::TestBuildSearchHomologGroupsSummary -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add top_cyanorak_roles/top_cog_categories to summary builders"
```

---

### Task 4: Verify Cypher against live KG

**Prerequisite:** KG must be running at localhost:7687.

Run each modified builder against the live graph and verify output shape. This catches Cypher bugs before building the API/MCP layers on top.

- [ ] **Step 1: Verify filter builders**

```bash
uv run python -c "
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.queries_lib import (
    build_gene_homologs, build_search_homolog_groups,
)
conn = GraphConnection()

# EXISTS filter on search_homolog_groups
cypher, params = build_search_homolog_groups(
    search_text='photosystem', cyanorak_roles=['cyanorak.role:J.8'])
r = conn.execute_query(cypher, **params)
assert len(r) > 0, 'Expected results for photosystem + J.8 filter'
print(f'search filter: {len(r)} rows, first={r[0][\"group_id\"]}')

# EXISTS filter on gene_homologs
cypher, params = build_gene_homologs(
    locus_tags=['PMM0532'], cyanorak_roles=['cyanorak.role:H.2'])
r = conn.execute_query(cypher, **params)
assert len(r) > 0, 'Expected results for PMM0532 + H.2 filter'
print(f'gene_homologs filter: {len(r)} rows')

# Both filters (AND)
cypher, params = build_search_homolog_groups(
    search_text='photosystem',
    cyanorak_roles=['cyanorak.role:J.8'],
    cog_categories=['cog.category:S'])
r = conn.execute_query(cypher, **params)
print(f'both filters AND: {len(r)} rows')

print('PASS: all filter queries executed successfully')
"
```

Expected: All queries return results, no errors.

- [ ] **Step 2: Verify verbose builders**

```bash
uv run python -c "
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.queries_lib import (
    build_gene_homologs, build_search_homolog_groups,
)
conn = GraphConnection()

# Verbose search_homolog_groups
cypher, params = build_search_homolog_groups(
    search_text='photosystem', verbose=True, limit=3)
r = conn.execute_query(cypher, **params)
assert len(r) > 0
row = r[0]
assert 'cyanorak_roles' in row, f'Missing cyanorak_roles, keys={row.keys()}'
assert 'cog_categories' in row, f'Missing cog_categories, keys={row.keys()}'
assert isinstance(row['cyanorak_roles'], list)
print(f'search verbose: roles={row[\"cyanorak_roles\"]}, cogs={row[\"cog_categories\"]}')

# Verbose gene_homologs
cypher, params = build_gene_homologs(
    locus_tags=['PMM0532'], verbose=True)
r = conn.execute_query(cypher, **params)
assert len(r) > 0
row = r[0]
assert 'cyanorak_roles' in row
assert isinstance(row['cyanorak_roles'], list)
print(f'gene_homologs verbose: roles={row[\"cyanorak_roles\"]}, cogs={row[\"cog_categories\"]}')

# Empty list for unannotated group
cypher, params = build_search_homolog_groups(
    search_text='hypothetical', verbose=True, limit=20)
r = conn.execute_query(cypher, **params)
empty = [x for x in r if len(x['cyanorak_roles']) == 0]
assert len(empty) > 0, 'Expected at least one group with empty roles'
print(f'empty roles confirmed: {len(empty)} groups with no annotations')

print('PASS: all verbose queries return correct structure')
"
```

Expected: `{id, name}` dicts in lists; empty `[]` for unannotated groups.

- [ ] **Step 3: Verify summary builders**

```bash
uv run python -c "
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.queries_lib import (
    build_gene_homologs_summary, build_search_homolog_groups_summary,
)
conn = GraphConnection()

# search_homolog_groups summary
cypher, params = build_search_homolog_groups_summary(search_text='photosystem')
r = conn.execute_query(cypher, **params)[0]
assert 'top_cyanorak_roles' in r, f'Missing key, got {r.keys()}'
assert 'top_cog_categories' in r
assert isinstance(r['top_cyanorak_roles'], list)
assert len(r['top_cyanorak_roles']) <= 5
if r['top_cyanorak_roles']:
    item = r['top_cyanorak_roles'][0]
    assert 'id' in item and 'name' in item and 'count' in item, f'Bad shape: {item}'
print(f'search summary: {len(r[\"top_cyanorak_roles\"])} roles, {len(r[\"top_cog_categories\"])} cogs')
print(f'  roles: {r[\"top_cyanorak_roles\"]}')

# gene_homologs summary
cypher, params = build_gene_homologs_summary(locus_tags=['PMM0532', 'PMM0150', 'PMM1425'])
r = conn.execute_query(cypher, **params)[0]
assert 'top_cyanorak_roles' in r
assert 'top_cog_categories' in r
print(f'gene_homologs summary: {len(r[\"top_cyanorak_roles\"])} roles, {len(r[\"top_cog_categories\"])} cogs')
print(f'  roles: {r[\"top_cyanorak_roles\"]}')

print('PASS: all summary queries return correct top-5 shape')
"
```

Expected: Each returns `top_cyanorak_roles` and `top_cog_categories` as lists of `{id, name, count}` dicts, max 5 items.

- [ ] **Step 4: Fix any Cypher issues found, re-run unit tests, commit fixes**

If any verification step fails, fix the Cypher in queries_lib.py, re-run unit tests, then re-verify.

```bash
pytest tests/unit/test_query_builders.py -v
```

---

### Task 5: API layer — `search_homolog_groups`

**Files:**
- Modify: `multiomics_explorer/api/functions.py:888-1001`
- Test: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing tests**

Add to `TestSearchHomologGroups` in `tests/unit/test_api_functions.py`:

```python
def test_passes_ontology_filters(self, mock_conn):
    mock_conn.execute_query.side_effect = [
        [{"total_entries": 21122, "total_matching": 0,
          "score_max": None, "score_median": None,
          "by_source": [], "by_level": [],
          "top_cyanorak_roles": [], "top_cog_categories": []}],
    ]
    api.search_homolog_groups(
        "test", cyanorak_roles=["cyanorak.role:G.3"],
        cog_categories=["cog.category:J"], summary=True, conn=mock_conn)
    call_args = mock_conn.execute_query.call_args
    cypher = call_args[0][0]
    assert "Og_has_cyanorak_role" in cypher
    assert "Og_in_cog_category" in cypher

def test_summary_includes_top_ontology(self, mock_conn):
    mock_conn.execute_query.side_effect = [
        [{"total_entries": 21122, "total_matching": 5,
          "score_max": 3.5, "score_median": 2.0,
          "by_source": [], "by_level": [],
          "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 3}],
          "top_cog_categories": [{"id": "cog.category:C", "name": "Energy prod", "count": 2}]}],
    ]
    result = api.search_homolog_groups("test", summary=True, conn=mock_conn)
    assert len(result["top_cyanorak_roles"]) == 1
    assert result["top_cyanorak_roles"][0]["id"] == "cyanorak.role:G.3"
    assert len(result["top_cog_categories"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_api_functions.py::TestSearchHomologGroups::test_passes_ontology_filters -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'cyanorak_roles'`

- [ ] **Step 3: Implement API changes**

In `multiomics_explorer/api/functions.py:888`, add `cyanorak_roles` and `cog_categories` to the function signature:

```python
def search_homolog_groups(
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
```

Update `filter_kwargs` (line 937) to include new params:

```python
    filter_kwargs = dict(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles, cog_categories=cog_categories,
    )
```

Update `envelope` construction (line 964) to include the new summary fields:

```python
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_source": _rename_freq(raw_summary["by_source"], "source"),
        "by_level": _rename_freq(raw_summary["by_level"], "taxonomic_level"),
        "score_max": raw_summary["score_max"],
        "score_median": raw_summary["score_median"],
        "top_cyanorak_roles": raw_summary["top_cyanorak_roles"],
        "top_cog_categories": raw_summary["top_cog_categories"],
    }
```

Update docstring to mention new params and keys.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_api_functions.py::TestSearchHomologGroups -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "feat: add ontology filters and summary fields to search_homolog_groups API"
```

---

### Task 6: API layer — `gene_homologs`

**Files:**
- Modify: `multiomics_explorer/api/functions.py:390-487`
- Test: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing tests**

Add to `TestGeneHomologs` in `tests/unit/test_api_functions.py`:

```python
def test_summary_includes_top_ontology(self, mock_conn):
    mock_conn.execute_query.side_effect = [
        [{"total_matching": 3,
          "by_organism": [{"item": "Prochlorococcus MED4", "count": 3}],
          "by_source": [{"item": "cyanorak", "count": 2}],
          "not_found": [], "no_groups": [],
          "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 2}],
          "top_cog_categories": []}],
    ]
    result = api.gene_homologs(["PMM0845"], summary=True, conn=mock_conn)
    assert "top_cyanorak_roles" in result
    assert len(result["top_cyanorak_roles"]) == 1
    assert "top_cog_categories" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_api_functions.py::TestGeneHomologs::test_summary_includes_top_ontology -v`
Expected: FAIL — `KeyError: 'top_cyanorak_roles'`

- [ ] **Step 3: Implement API changes**

In `multiomics_explorer/api/functions.py:390`, the `gene_homologs` signature stays the same (no new filter params per spec — `gene_homologs` doesn't get ontology filters, only verbose output and summary breakdowns).

Update `envelope` construction (line 461) to include new summary fields:

```python
    envelope = {
        "total_matching": raw_summary["total_matching"],
        "by_organism": _sorted_breakdown(raw_summary["by_organism"], "organism_name"),
        "by_source": _sorted_breakdown(raw_summary["by_source"], "source"),
        "not_found": raw_summary["not_found"],
        "no_groups": raw_summary["no_groups"],
        "top_cyanorak_roles": raw_summary["top_cyanorak_roles"],
        "top_cog_categories": raw_summary["top_cog_categories"],
    }
```

Update docstring to mention new keys.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_api_functions.py::TestGeneHomologs -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "feat: add top_cyanorak_roles/top_cog_categories to gene_homologs API"
```

---

### Task 7: MCP layer — `search_homolog_groups`

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py:1686-1808`
- Test: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Write failing tests**

Add to `TestSearchHomologGroupsWrapper` in `tests/unit/test_tool_wrappers.py`:

```python
@pytest.mark.asyncio
async def test_ontology_filters_forwarded(self, tool_fns, mock_ctx):
    api_return = {
        **self._SAMPLE_API_RETURN,
        "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 3}],
        "top_cog_categories": [],
    }
    with patch(
        "multiomics_explorer.api.functions.search_homolog_groups",
        return_value=api_return,
    ) as mock_api:
        await tool_fns["search_homolog_groups"](
            mock_ctx, search_text="photosynthesis",
            cyanorak_roles=["cyanorak.role:G.3"],
            cog_categories=["cog.category:J"],
        )
    call_kwargs = mock_api.call_args.kwargs
    assert call_kwargs["cyanorak_roles"] == ["cyanorak.role:G.3"]
    assert call_kwargs["cog_categories"] == ["cog.category:J"]

@pytest.mark.asyncio
async def test_ontology_summary_in_response(self, tool_fns, mock_ctx):
    api_return = {
        **self._SAMPLE_API_RETURN,
        "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 3}],
        "top_cog_categories": [{"id": "cog.category:C", "name": "Energy prod", "count": 2}],
    }
    with patch(
        "multiomics_explorer.api.functions.search_homolog_groups",
        return_value=api_return,
    ):
        result = await tool_fns["search_homolog_groups"](
            mock_ctx, search_text="photosynthesis",
        )
    assert len(result.top_cyanorak_roles) == 1
    assert result.top_cyanorak_roles[0].id == "cyanorak.role:G.3"
    assert len(result.top_cog_categories) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tool_wrappers.py::TestSearchHomologGroupsWrapper::test_ontology_filters_forwarded -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'cyanorak_roles'`

- [ ] **Step 3: Add Pydantic models and update wrapper**

In `multiomics_explorer/mcp_server/tools.py`, add a new breakdown model near line 1715 (after `SearchHomologGroupsLevelBreakdown`):

```python
    class OntologyBreakdown(BaseModel):
        id: str = Field(description="Ontology term ID (e.g. 'cyanorak.role:G.3')")
        name: str = Field(description="Ontology term name (e.g. 'Energy metabolism > Electron transport')")
        count: int = Field(description="Groups with this annotation (e.g. 42)")
```

Add ontology columns to `SearchHomologGroupsResult` (after `has_cross_genus_members`, line ~1707):

```python
        cyanorak_roles: list[dict] | None = Field(default=None,
            description="Consensus Cyanorak roles [{id, name}]. Verbose only.")
        cog_categories: list[dict] | None = Field(default=None,
            description="Consensus COG categories [{id, name}]. Verbose only.")
```

Add summary fields to `SearchHomologGroupsResponse` (after `score_median`, line ~1727):

```python
        top_cyanorak_roles: list[OntologyBreakdown] = Field(
            default_factory=list,
            description="Top 5 CyanorakRole annotations by frequency")
        top_cog_categories: list[OntologyBreakdown] = Field(
            default_factory=list,
            description="Top 5 CogFunctionalCategory annotations by frequency")
```

Add filter params to the `search_homolog_groups` function signature (after `max_specificity_rank`, line ~1755):

```python
        cyanorak_roles: Annotated[list[str] | None, Field(
            description="Filter by CyanorakRole term IDs. OR within list. "
            "E.g. ['cyanorak.role:G.3', 'cyanorak.role:J.8'].",
        )] = None,
        cog_categories: Annotated[list[str] | None, Field(
            description="Filter by CogFunctionalCategory term IDs. OR within list. "
            "E.g. ['cog.category:C', 'cog.category:J'].",
        )] = None,
```

Update the API call (line ~1780) to pass the new params:

```python
            data = api.search_homolog_groups(
                search_text, source=source,
                taxonomic_level=taxonomic_level,
                max_specificity_rank=max_specificity_rank,
                cyanorak_roles=cyanorak_roles,
                cog_categories=cog_categories,
                summary=summary, verbose=verbose, limit=limit, offset=offset, conn=conn,
            )
```

Update the response construction (line ~1789) to include the new fields:

```python
            top_cr = [OntologyBreakdown(**b) for b in data.get("top_cyanorak_roles", [])]
            top_cc = [OntologyBreakdown(**b) for b in data.get("top_cog_categories", [])]
            response = SearchHomologGroupsResponse(
                total_entries=data["total_entries"],
                total_matching=data["total_matching"],
                by_source=by_source,
                by_level=by_level,
                score_max=data["score_max"],
                score_median=data["score_median"],
                top_cyanorak_roles=top_cr,
                top_cog_categories=top_cc,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
```

Update the tool docstring to mention the new filter and verbose capabilities.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tool_wrappers.py::TestSearchHomologGroupsWrapper -v`
Expected: ALL PASS

- [ ] **Step 5: Update `_SAMPLE_API_RETURN` in existing tests**

The existing `_SAMPLE_API_RETURN` dict at line 2357 needs the new keys to avoid failures in other tests:

Add to the dict:
```python
        "top_cyanorak_roles": [],
        "top_cog_categories": [],
```

- [ ] **Step 6: Run full test class to verify no regressions**

Run: `pytest tests/unit/test_tool_wrappers.py::TestSearchHomologGroupsWrapper -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat: add ontology filters and summary to search_homolog_groups MCP tool"
```

---

### Task 8: MCP layer — `gene_homologs`

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py:520-635`
- Test: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Write failing tests**

Add to `TestGeneHomologsWrapper` in `tests/unit/test_tool_wrappers.py`:

```python
@pytest.mark.asyncio
async def test_ontology_summary_in_response(self, tool_fns, mock_ctx):
    api_return = {
        "total_matching": 3,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 3}],
        "by_source": [{"source": "cyanorak", "count": 2}],
        "returned": 0,
        "truncated": True,
        "not_found": [],
        "no_groups": [],
        "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 2}],
        "top_cog_categories": [],
        "results": [],
    }
    with patch(
        "multiomics_explorer.api.functions.gene_homologs",
        return_value=api_return,
    ):
        result = await tool_fns["gene_homologs"](
            mock_ctx, locus_tags=["PMM0845"], summary=True,
        )
    assert len(result.top_cyanorak_roles) == 1
    assert result.top_cyanorak_roles[0].id == "cyanorak.role:G.3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_wrappers.py::TestGeneHomologsWrapper::test_ontology_summary_in_response -v`
Expected: FAIL — `AttributeError: 'GeneHomologsResponse' has no attribute 'top_cyanorak_roles'`

- [ ] **Step 3: Add Pydantic model fields and update wrapper**

In `multiomics_explorer/mcp_server/tools.py`, add ontology columns to `GeneHomologResult` (after `functional_description`, line ~535):

```python
        cyanorak_roles: list[dict] | None = Field(default=None,
            description="Consensus Cyanorak roles [{id, name}]. Verbose only.")
        cog_categories: list[dict] | None = Field(default=None,
            description="Consensus COG categories [{id, name}]. Verbose only.")
```

Reuse the `OntologyBreakdown` model (defined in Task 7) for summary fields. Add to `GeneHomologsResponse` (after `no_groups`, line ~553):

```python
        top_cyanorak_roles: list[OntologyBreakdown] = Field(
            default_factory=list,
            description="Top 5 CyanorakRole annotations by frequency")
        top_cog_categories: list[OntologyBreakdown] = Field(
            default_factory=list,
            description="Top 5 CogFunctionalCategory annotations by frequency")
```

Note: `OntologyBreakdown` was defined in Task 7 — it will be in scope since all models are nested in the `register_tools` function.

Update the response construction in the `gene_homologs` wrapper (line ~615):

```python
            top_cr = [OntologyBreakdown(**b) for b in data.get("top_cyanorak_roles", [])]
            top_cc = [OntologyBreakdown(**b) for b in data.get("top_cog_categories", [])]
            response = GeneHomologsResponse(
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_source=by_source,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                not_found=data["not_found"],
                no_groups=data["no_groups"],
                top_cyanorak_roles=top_cr,
                top_cog_categories=top_cc,
                results=results,
            )
```

Update the tool docstring to mention new verbose output columns.

- [ ] **Step 4: Update existing test fixtures**

Existing tests in `TestGeneHomologsWrapper` that mock the API return need the new keys. Find any `_SAMPLE_API_RETURN` or inline mock dicts and add:

```python
        "top_cyanorak_roles": [],
        "top_cog_categories": [],
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_tool_wrappers.py::TestGeneHomologsWrapper -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat: add ontology summary and verbose columns to gene_homologs MCP tool"
```

---

### Task 9: Integration tests — CyVer + API contracts

**Files:**
- Modify: `tests/integration/test_cyver_queries.py:187-205`
- Modify: `tests/integration/test_api_contract.py:142-163, 598-638`

- [ ] **Step 1: Add CyVer builder variants with ontology params**

In `tests/integration/test_cyver_queries.py`, add new entries to `_BUILDERS` (after line 205):

```python
    # --- homologs with ontology filters ---
    ("gene_homologs_summary_ont", build_gene_homologs_summary,
     {"locus_tags": _LOCUS, "cyanorak_roles": ["cyanorak.role:G.3"]}),
    ("gene_homologs_ont", build_gene_homologs,
     {"locus_tags": _LOCUS, "cyanorak_roles": ["cyanorak.role:G.3"]}),
    ("gene_homologs_verbose", build_gene_homologs,
     {"locus_tags": _LOCUS, "verbose": True}),
    ("search_homolog_groups_summary_ont", build_search_homolog_groups_summary,
     {"search_text": "photosystem", "cog_categories": ["cog.category:C"]}),
    ("search_homolog_groups_ont", build_search_homolog_groups,
     {"search_text": "photosystem", "cyanorak_roles": ["cyanorak.role:G.3"]}),
    ("search_homolog_groups_verbose", build_search_homolog_groups,
     {"search_text": "photosystem", "verbose": True}),
```

Add new map keys to `_KNOWN_MAP_KEYS` (line 114):

```python
_KNOWN_MAP_KEYS = {
    "org", "cat", "lt", "cnt", "terms", "srcs", "gid",
    "org_input", "tt", "ts", "eid", "status", "log2fc", "m",
    "tpo", "tph", "tp", "nf_raw", "ng_raw", "nm_raw",
    "cr_id", "cr_name", "cc_id", "cc_name", "og_ids", "src", "lvl",
}
```

- [ ] **Step 2: Add API contract tests for new keys**

In `tests/integration/test_api_contract.py`, add to `TestGeneHomologsContract`:

```python
def test_summary_has_ontology_keys(self, conn):
    result = api.gene_homologs([KNOWN_GENE], summary=True, conn=conn)
    assert "top_cyanorak_roles" in result
    assert "top_cog_categories" in result
    for item in result["top_cyanorak_roles"]:
        assert "id" in item
        assert "name" in item
        assert "count" in item

def test_verbose_has_ontology_columns(self, conn):
    result = api.gene_homologs([KNOWN_GENE], verbose=True, limit=1, conn=conn)
    row = result["results"][0]
    assert "cyanorak_roles" in row
    assert "cog_categories" in row
    assert isinstance(row["cyanorak_roles"], list)
    assert isinstance(row["cog_categories"], list)
```

Add to `TestSearchHomologGroupsContract`:

```python
def test_summary_has_ontology_keys(self, conn):
    result = api.search_homolog_groups("photosynthesis", summary=True, conn=conn)
    assert "top_cyanorak_roles" in result
    assert "top_cog_categories" in result

def test_verbose_has_ontology_columns(self, conn):
    result = api.search_homolog_groups(
        "photosynthesis", verbose=True, limit=1, conn=conn)
    row = result["results"][0]
    assert "cyanorak_roles" in row
    assert "cog_categories" in row
    assert isinstance(row["cyanorak_roles"], list)

def test_ontology_filter(self, conn):
    result = api.search_homolog_groups(
        "photosystem", cyanorak_roles=["cyanorak.role:J.8"],
        summary=True, conn=conn)
    assert result["total_matching"] >= 1
```

Update `test_returns_dict_envelope` in `TestSearchHomologGroupsContract` to include new expected keys:

```python
        expected_keys = {
            "total_entries", "total_matching", "by_source", "by_level",
            "score_max", "score_median",
            "top_cyanorak_roles", "top_cog_categories",
            "returned", "truncated", "offset", "results",
        }
```

Update `test_returns_dict_with_envelope` in `TestGeneHomologsContract`:

```python
        for key in ("total_matching", "by_organism", "by_source",
                     "returned", "truncated", "offset", "not_found", "no_groups",
                     "top_cyanorak_roles", "top_cog_categories", "results"):
            assert key in result
```

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_cyver_queries.py tests/integration/test_api_contract.py
git commit -m "test: add integration tests for ontology on ortholog groups"
```

---

### Task 10: Update YAML tool definitions and re-export

**Files:**
- Modify: `multiomics_explorer/inputs/tools/search_homolog_groups.yaml`
- Modify: `multiomics_explorer/inputs/tools/gene_homologs.yaml`
- Modify: `multiomics_explorer/__init__.py` (if `search_homolog_groups` signature changed)

- [ ] **Step 1: Update search_homolog_groups.yaml**

Add new verbose fields and update examples:

```yaml
verbose_fields:
  - description
  - functional_description
  - genera
  - has_cross_genus_members
  - cyanorak_roles
  - cog_categories
```

Add an example for ontology filtering:

```yaml
  - title: Filter by CyanorakRole
    call: search_homolog_groups(search_text="transport", cyanorak_roles=["cyanorak.role:D.1.5"])
```

- [ ] **Step 2: Update gene_homologs.yaml**

Add new verbose fields:

```yaml
verbose_fields:
  - member_count
  - organism_count
  - genera
  - has_cross_genus_members
  - description
  - functional_description
  - cyanorak_roles
  - cog_categories
```

- [ ] **Step 3: Re-export from `__init__.py` if needed**

Check if `multiomics_explorer/__init__.py` re-exports `search_homolog_groups`. The signature changed (new params), but since Python re-exports don't need signature updates, this should be automatic. Verify:

Run: `python -c "from multiomics_explorer import search_homolog_groups; import inspect; print(inspect.signature(search_homolog_groups))"`

- [ ] **Step 4: Rebuild about content**

Run: `uv run python scripts/build_about_content.py`

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/inputs/tools/ multiomics_explorer/skills/
git commit -m "docs: update tool YAMLs and about content for ontology on ortholog groups"
```

---

### Task 11: Run full test suite and verify

- [ ] **Step 1: Run unit tests**

Run: `pytest tests/unit/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run integration tests (KG must be up)**

Run: `pytest -m kg -v`
Expected: ALL PASS

- [ ] **Step 3: Run CyVer tests specifically**

Run: `pytest tests/integration/test_cyver_queries.py -m kg -v`
Expected: ALL PASS (new builder variants validate against live schema)

- [ ] **Step 4: Quick MCP smoke test**

Restart MCP server and test with a tool call:

```
/mcp
```

Then invoke:
- `search_homolog_groups(search_text="photosystem", verbose=True, limit=2)` — verify `cyanorak_roles`/`cog_categories` in results
- `search_homolog_groups(search_text="transport", cyanorak_roles=["cyanorak.role:D.1.5"], limit=3)` — verify filter works
- `gene_homologs(locus_tags=["PMM0532"], verbose=True)` — verify ontology columns
- `gene_homologs(locus_tags=["PMM0532", "PMM0150"], summary=True)` — verify `top_cyanorak_roles`/`top_cog_categories`

- [ ] **Step 5: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address any issues from full test run"
```
