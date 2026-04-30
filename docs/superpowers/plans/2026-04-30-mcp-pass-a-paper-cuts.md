# MCP Pass A paper-cuts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the five KG-independent paper-cut items from the MCP usability audit (F-AUDIT-1, F-AUDIT-2 layer 1, F-AUDIT-3, `list_experiments.authors`, rubric promotion) as a single bundled change so the explorer is more usable before the KG round-trip.

**Architecture:** Three of the five items are doc-only — they touch the LLM-facing Pydantic field descriptions and tool docstrings in [`mcp_server/tools.py`](../../multiomics_explorer/mcp_server/tools.py), then regenerate the about-content under [`skills/multiomics-kg-guide/references/tools/`](../../multiomics_explorer/skills/multiomics-kg-guide/references/tools/). One item (`list_experiments.authors`) is a small full 4-layer pass per `layer-rules` — query builder → API → MCP wrapper → YAML/about → tests. The last item (rubric) is a skill-doc addition.

**Tech Stack:** Python 3.11, Pydantic v2, FastMCP, Neo4j Cypher (APOC), pytest, `uv`. Build pattern follows the established `add-or-update-tool` skill.

**Source spec:** [`docs/superpowers/specs/2026-04-29-mcp-usability-audit.md`](../specs/2026-04-29-mcp-usability-audit.md)

---

## Pre-work

The plan assumes you start on a clean branch from `main`. The bundle is small (~1–2 hours, single PR); a worktree is optional. Run from the repo root `/home/osnat/github/multiomics_explorer`.

### Task 0: Branch setup

**Files:** none (git only)

- [ ] **Step 1: Confirm clean working tree**

```bash
git status
```
Expected: `nothing to commit, working tree clean` and `On branch main`.

- [ ] **Step 2: Create branch**

```bash
git checkout -b feat/mcp-pass-a-paper-cuts
```

- [ ] **Step 3: Confirm branch**

```bash
git branch --show-current
```
Expected: `feat/mcp-pass-a-paper-cuts`.

---

## Section 1 — Doc-only edits (items 1, 2, 3)

These tasks touch only LLM-facing prose in [`mcp_server/tools.py`](../../multiomics_explorer/mcp_server/tools.py): Pydantic field descriptions and tool docstrings. No queries, no api logic, no behavior changes.

For TDD discipline on doc edits: run the about-content consistency tests after every edit batch — they catch malformed `Field(description=...)` strings, missing fields, or schema regressions. New behavioral tests are not required for description edits; the audit-finding text itself is the spec.

### Task 1: F-AUDIT-1 — replace placeholder examples in `GeneOverviewResult`

**Files:**
- Modify: [`multiomics_explorer/mcp_server/tools.py:838-839`](../../multiomics_explorer/mcp_server/tools.py#L838-L839)

Replace placeholder strings (`'Alternative locus ID'`) in two field examples with real, content-bearing values. Real values were sourced from a live KG query against MED4 (`PMM1353` / `prmA`) on 2026-04-30 — see KG-side requirements doc.

- [ ] **Step 1: Read the current lines to confirm context**

```bash
sed -n '836,841p' multiomics_explorer/mcp_server/tools.py
```
Expected to see the two `Field(description=...)` strings containing `Alternative locus ID`.

- [ ] **Step 2: Edit `gene_summary` example**

In [`multiomics_explorer/mcp_server/tools.py`](../../multiomics_explorer/mcp_server/tools.py) replace:

```python
        gene_summary: str | None = Field(default=None, description="Concatenated summary text (e.g. 'dnaN :: DNA polymerase III subunit beta :: Alternative locus ID')")
```

with:

```python
        gene_summary: str | None = Field(default=None, description="Concatenated summary text (e.g. 'prmA :: ribosomal protein L11 methyltransferase :: Methylates ribosomal protein L11')")
```

- [ ] **Step 3: Edit `function_description` example**

Replace:

```python
        function_description: str | None = Field(default=None, description="Curated functional description (e.g. 'Alternative locus ID')")
```

with:

```python
        function_description: str | None = Field(default=None, description="Curated functional description (e.g. 'Methylates ribosomal protein L11'). May be null when no curated text exists.")
```

- [ ] **Step 4: Verify no `'Alternative locus ID'` strings remain in tools.py field descriptions**

```bash
grep -n "Alternative locus ID" multiomics_explorer/mcp_server/tools.py
```
Expected: no output.

- [ ] **Step 5: Run unit test for the wrapper to confirm Pydantic still parses**

```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestGeneOverviewWrapper -v
```
Expected: PASS (no behavior change; only descriptions edited).

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "fix(gene_overview): replace placeholder example strings in Pydantic field descriptions

F-AUDIT-1 from MCP usability audit. The 'Alternative locus ID' placeholder
was the same KG-side stub the trigger analysis flagged in F5; using it as
the field example was training the LLM to expect it as content.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: F-AUDIT-2 layer 1 — tighten `annotation_types` description

**Files:**
- Modify: [`multiomics_explorer/mcp_server/tools.py:820`](../../multiomics_explorer/mcp_server/tools.py#L820)

The current description ("Ontology types with annotations (e.g. ['go_bp', 'ec', 'kegg'])") doesn't tell the LLM that this is a presence-only signal. F2 in the trigger analysis was a direct consequence of treating it as a content-informativeness signal.

- [ ] **Step 1: Edit `annotation_types` description**

Replace:

```python
        annotation_types: list[str] = Field(default_factory=list, description="Ontology types with annotations (e.g. ['go_bp', 'ec', 'kegg'])")
```

with:

```python
        annotation_types: list[str] = Field(default_factory=list, description="Ontology source types where this gene has at least one annotation (e.g. ['go_bp', 'ec', 'kegg']). Presence-only — does NOT indicate content informativeness; a 'cog_category' entry may be 'Function unknown'. For term content, call gene_ontology_terms.")
```

- [ ] **Step 2: Run wrapper tests**

```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestGeneOverviewWrapper -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "fix(gene_overview): clarify annotation_types is presence-only, not content

F-AUDIT-2 layer 1 from MCP usability audit. annotation_types is a per-source
presence flag and does not predict term informativeness — F2 in the trigger
analysis was a direct over-extension of this field. Description now flags
the limitation and points to gene_ontology_terms for content.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: F-AUDIT-3a — add drill-down clauses to `GeneOverviewResult` summary fields

**Files:**
- Modify: [`multiomics_explorer/mcp_server/tools.py:821-827`](../../multiomics_explorer/mcp_server/tools.py#L821-L827)

Five fields need a one-line drill-down pointer. The pattern is already established at line 835 for `derived_metric_value_kinds`: `"Use to route to genes_by_{kind}_metric drill-downs."`

- [ ] **Step 1: Edit `expression_edge_count` description**

Replace:

```python
        expression_edge_count: int = Field(default=0, description="Number of expression data points (e.g. 36)")
```

with:

```python
        expression_edge_count: int = Field(default=0, description="Number of expression data points (e.g. 36). When > 0, drill into differential_expression_by_gene or gene_response_profile.")
```

- [ ] **Step 2: Edit `significant_up_count` and `significant_down_count` descriptions**

Replace:

```python
        significant_up_count: int = Field(default=0, description="Significant up-regulated DE observations (e.g. 3)")
        significant_down_count: int = Field(default=0, description="Significant down-regulated DE observations (e.g. 2)")
```

with:

```python
        significant_up_count: int = Field(default=0, description="Significant up-regulated DE observations (e.g. 3). When > 0, use differential_expression_by_gene with direction='up' for per-experiment detail.")
        significant_down_count: int = Field(default=0, description="Significant down-regulated DE observations (e.g. 2). When > 0, use differential_expression_by_gene with direction='down' for per-experiment detail.")
```

- [ ] **Step 3: Edit `closest_ortholog_group_size` and `closest_ortholog_genera` descriptions**

Replace:

```python
        closest_ortholog_group_size: int | None = Field(default=None, description="Size of tightest ortholog group (e.g. 9)")
        closest_ortholog_genera: list[str] | None = Field(default=None, description="Genera in tightest ortholog group (e.g. ['Prochlorococcus', 'Synechococcus'])")
```

with:

```python
        closest_ortholog_group_size: int | None = Field(default=None, description="Size of tightest ortholog group (e.g. 9). Use gene_homologs for full per-group membership and source/level metadata.")
        closest_ortholog_genera: list[str] | None = Field(default=None, description="Genera in tightest ortholog group (e.g. ['Prochlorococcus', 'Synechococcus']). Use gene_homologs for full membership; genes_by_homolog_group to expand a specific group.")
```

- [ ] **Step 4: Edit `cluster_membership_count` and `cluster_types` descriptions**

Replace:

```python
        cluster_membership_count: int = Field(default=0, description="Number of cluster memberships (e.g. 3)")
        cluster_types: list[str] = Field(default_factory=list, description="Distinct cluster types (e.g. ['condition_comparison', 'diel'])")
```

with:

```python
        cluster_membership_count: int = Field(default=0, description="Number of cluster memberships (e.g. 3). When > 0, drill into gene_clusters_by_gene for per-cluster details.")
        cluster_types: list[str] = Field(default_factory=list, description="Distinct cluster types (e.g. ['condition_comparison', 'diel']). Use gene_clusters_by_gene with cluster_type filter to scope drill-down.")
```

- [ ] **Step 5: Run wrapper tests**

```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestGeneOverviewWrapper -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "fix(gene_overview): add downstream drill-down clauses to summary fields

F-AUDIT-3a from MCP usability audit. The DM fields already follow the
'use this signal to route to <tool>' pattern (see derived_metric_value_kinds
field). Promote that pattern to expression, ortholog, and cluster summary
fields so the LLM sees the drill-down tool by name when the signal is present.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: F-AUDIT-3b — add downstream-direction trailers to summary-tool docstrings

**Files:**
- Modify: [`multiomics_explorer/mcp_server/tools.py`](../../multiomics_explorer/mcp_server/tools.py) (six docstrings)

Six summary tools currently have "use after X" upstream pointers but no "after this, drill into Y" downstream pointers. Pattern from [`gene_details:978-979`](../../multiomics_explorer/mcp_server/tools.py#L978-L979):

```
For organism taxonomy, use list_organisms. For homologs, use
gene_homologs. For ontology annotations, use gene_ontology_terms.
```

The six docstrings to update sit at lines:
- `gene_overview` (line 904)
- `list_organisms` (line 537)
- `list_publications` (line 1631)
- `list_experiments` (line 1860)
- `list_clustering_analyses` (line 3357)
- `list_derived_metrics` (line 3863)

- [ ] **Step 1: Update `gene_overview` docstring**

Locate the docstring starting at line 904 (`async def gene_overview`). Replace:

```python
        """Get an overview of genes: identity and data availability signals.

        Use after resolve_gene, genes_by_function, genes_by_ontology, or
        gene_homologs to understand what each gene is and what follow-up
        data exists.
        """
```

with:

```python
        """Get an overview of genes: identity and data availability signals.

        Use after resolve_gene, genes_by_function, genes_by_ontology, or
        gene_homologs to understand what each gene is and what follow-up
        data exists.

        After this tool, drill into the rich axes when the per-gene signal
        is present: gene_ontology_terms (when annotation_types is non-empty),
        gene_homologs (when closest_ortholog_group_size > 0),
        gene_clusters_by_gene (when cluster_membership_count > 0),
        differential_expression_by_gene or gene_response_profile (when
        expression_edge_count > 0), gene_derived_metrics (when
        derived_metric_count > 0).
        """
```

- [ ] **Step 2: Update `list_organisms` docstring**

Locate the docstring inside the `async def list_organisms` function near line 537. Find its existing trailing prose (read the lines around 537–546 first) and append a new paragraph at the end of the docstring:

```
After this tool, scope deeper queries to the chosen organism via the
organism / locus_tags filters on per-gene tools (gene_overview,
gene_ontology_terms, gene_homologs) and on list_experiments
/ list_publications. Use list_filter_values for categorical
field enumeration.
```

- [ ] **Step 3: Update `list_publications` docstring**

Locate the docstring at line 1679 (`"""List publications with expression data in the knowledge graph...`). Replace:

```python
        """List publications with expression data in the knowledge graph.

        Returns publication metadata and experiment summaries. Use this as
        an entry point to discover what studies exist, then drill into
        specific experiments with list_experiments or genes with genes_by_function.
        """
```

with:

```python
        """List publications with expression data in the knowledge graph.

        Returns publication metadata and experiment summaries. Use this as
        an entry point to discover what studies exist.

        After this tool, drill in via:
        - list_experiments(publication_doi=[doi]) for per-experiment detail
        - genes_by_function / genes_by_ontology for in-publication gene discovery
        - list_clustering_analyses(publication_doi=[doi]) for clustering analyses
        - list_derived_metrics(publication_doi=[doi]) for non-DE evidence
        """
```

- [ ] **Step 4: Update `list_experiments` docstring**

Locate the docstring inside `async def list_experiments` (line 1860). Append a downstream-pointers paragraph at the end of the existing docstring:

```
After this tool, drill in via:
- differential_expression_by_gene(experiment_ids=[id]) for per-gene DE
- list_clustering_analyses(experiment_ids=[id]) for clusters built from this experiment
- list_derived_metrics(experiment_ids=[id]) for DM evidence on this experiment
- pathway_enrichment(experiment_ids=[id]) for ORA on DE results
```

- [ ] **Step 5: Update `list_clustering_analyses` docstring**

Locate the docstring inside `async def list_clustering_analyses` (line 3357). Append:

```
After this tool, drill in via:
- genes_in_cluster(cluster_ids=[id]) for per-cluster member genes
- genes_in_cluster(analysis_id=...) for all clusters from one analysis
- gene_clusters_by_gene(locus_tags=[...], analysis_ids=[id]) to scope a
  per-gene cluster lookup to this analysis
```

- [ ] **Step 6: Update `list_derived_metrics` docstring**

Locate the docstring inside `async def list_derived_metrics` (line 3863). Append:

```
After this tool, drill in via:
- gene_derived_metrics(locus_tags=[...]) for per-gene DM lookup across all kinds
- genes_by_numeric_metric(derived_metric_ids=[id], ...) for numeric drill-down
- genes_by_boolean_metric(derived_metric_ids=[id], ...) for flag drill-down
- genes_by_categorical_metric(derived_metric_ids=[id], ...) for categorical drill-down
```

- [ ] **Step 7: Run wrapper tests for all six tools**

```bash
uv run pytest tests/unit/test_tool_wrappers.py -v -k "GeneOverview or ListOrganisms or ListPublications or ListExperiments or ListClusteringAnalyses or ListDerivedMetrics"
```
Expected: PASS — no behavior change.

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "fix(summary-tools): add downstream-direction docstring trailers

F-AUDIT-3b from MCP usability audit. Six summary tools (gene_overview,
list_organisms, list_publications, list_experiments,
list_clustering_analyses, list_derived_metrics) had upstream 'use after X'
pointers but no downstream 'after this, drill into Y'. Pattern model:
gene_details docstring lines 978-979.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Regenerate about-content for affected tools

**Files:**
- Generates: [`multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md`](../../multiomics_explorer/skills/multiomics-kg-guide/references/tools/)

Each Pydantic-model edit in Tasks 1–4 needs an about-content rebuild. The build script writes directly to the skills tree. There is no separate sync step.

- [ ] **Step 1: Run the about-content build for each affected tool**

```bash
uv run python scripts/build_about_content.py gene_overview
uv run python scripts/build_about_content.py list_organisms
uv run python scripts/build_about_content.py list_publications
uv run python scripts/build_about_content.py list_experiments
uv run python scripts/build_about_content.py list_clustering_analyses
uv run python scripts/build_about_content.py list_derived_metrics
```
Each command prints the destination path; expected: no errors.

- [ ] **Step 2: Verify the new descriptions are in the generated markdown**

```bash
grep -A1 "annotation_types" multiomics_explorer/skills/multiomics-kg-guide/references/tools/gene_overview.md | head -5
grep -A1 "drill into" multiomics_explorer/skills/multiomics-kg-guide/references/tools/gene_overview.md | head -10
```
Expected: see the new "presence-only" and "drill into" wording.

- [ ] **Step 3: Run about-content consistency tests**

```bash
uv run pytest tests/unit/test_about_content.py -v
```
Expected: PASS.

- [ ] **Step 4: Run integration about-examples tests (requires KG)**

```bash
uv run pytest tests/integration/test_about_examples.py -v -m kg
```
Expected: PASS (no examples were changed; tests verify they still execute).

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/tools/
git commit -m "chore(skills): regenerate about-content for Tasks 1-4 description edits

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Section 2 — Add `authors` field to `list_experiments` (item 4)

This is a 4-layer pass per `layer-rules`. The query already joins `Publication`, so adding `p.authors AS authors` to the RETURN columns is the only Cypher change. The api/ layer pass-through is already correct (it forwards builder-result rows verbatim); just update the docstring. Then add the typed Pydantic field, regenerate about-content, and update tests + regression baselines.

### Task 6: Add `authors` to query builder RETURN — TDD test first

**Files:**
- Modify: [`tests/unit/test_query_builders.py`](../../tests/unit/test_query_builders.py) (within `class TestBuildListExperiments` near line 2170)

- [ ] **Step 1: Locate the test class**

```bash
grep -n "class TestBuildListExperiments" tests/unit/test_query_builders.py
```
Expected: hit at line 2170.

- [ ] **Step 2: Add a failing test inside the class**

Insert this test method after `test_no_filters` (around line 2178):

```python
    def test_returns_authors_column(self):
        """RETURN columns include authors sourced from Publication.authors."""
        cypher, _ = build_list_experiments()
        assert "p.authors AS authors" in cypher
```

- [ ] **Step 3: Run the new test to confirm it fails**

```bash
uv run pytest tests/unit/test_query_builders.py::TestBuildListExperiments::test_returns_authors_column -v
```
Expected: FAIL — `assert "p.authors AS authors" in cypher` is False.

---

### Task 7: Implement `authors` in builder

**Files:**
- Modify: [`multiomics_explorer/kg/queries_lib.py`](../../multiomics_explorer/kg/queries_lib.py) — `build_list_experiments` near line 1347

- [ ] **Step 1: Add the column to compact RETURN block**

In `build_list_experiments`, locate the `return_cols` string (starts at line 1347 with `"e.id AS experiment_id,\n"`). After the line `"       p.doi AS publication_doi,\n"` (around line 1350), add:

```python
        "       coalesce(p.authors, []) AS authors,\n"
```

The line should now read:

```python
    return_cols = (
        "e.id AS experiment_id,\n"
        "       e.name AS experiment_name,\n"
        "       p.doi AS publication_doi,\n"
        "       coalesce(p.authors, []) AS authors,\n"
        "       e.organism_name AS organism_name,\n"
        ...
```

- [ ] **Step 2: Update the builder docstring**

In the same function (docstring starts at line 1281), update the compact RETURN keys list. Replace:

```
    RETURN keys (compact): experiment_id, experiment_name, publication_doi,
    organism_name, treatment_type, coculture_partner, omics_type,
```

with:

```
    RETURN keys (compact): experiment_id, experiment_name, publication_doi,
    authors, organism_name, treatment_type, coculture_partner, omics_type,
```

- [ ] **Step 3: Run the new test to confirm it passes**

```bash
uv run pytest tests/unit/test_query_builders.py::TestBuildListExperiments::test_returns_authors_column -v
```
Expected: PASS.

- [ ] **Step 4: Run the full test class to confirm no regressions**

```bash
uv run pytest tests/unit/test_query_builders.py::TestBuildListExperiments -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_query_builders.py multiomics_explorer/kg/queries_lib.py
git commit -m "feat(list_experiments): return authors from Publication

F-AUDIT-4 layer 1 from MCP usability audit. Builds-in the publication
authors join already present in the MATCH so consumers don't need a
separate list_publications call for author attribution.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Verify api/ layer passes through `authors` — test first

**Files:**
- Modify: [`tests/unit/test_api_functions.py`](../../tests/unit/test_api_functions.py) inside `class TestListExperiments` (line 2201)

The api function `list_experiments` calls `_run_detail()` which executes the builder query and `processed.append(r)`s each row dict verbatim. The new `authors` key from the builder will appear in `r` automatically. Tests must lock that behavior.

- [ ] **Step 1: Add a passthrough test**

Find `class TestListExperiments` at line 2201 in `tests/unit/test_api_functions.py`. Add this test method (study existing tests in the class first to match the mock-fixture pattern they use):

```python
    def test_authors_passes_through_from_builder(self, mock_conn):
        """Authors column from builder appears in api result rows verbatim."""
        # Mirror the structure used by sibling tests in this class.
        # mock_conn is the conftest fixture that returns a stub GraphConnection.
        from multiomics_explorer.api.functions import list_experiments

        # Stub: summary returns total + breakdowns; detail returns one row carrying authors.
        # Match the existing fixture style — see e.g. test_organism_filter in this class.
        # If the existing tests use a different fixture shape, adopt it here.
        mock_conn.execute_query.side_effect = [
            # _run_summary
            [{
                "total_matching": 1, "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "by_publication": [], "by_table_scope": [],
                "by_cluster_type": [], "by_growth_phase": [],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "time_course_count": 0,
            }],
            # build_list_experiments_summary() — total_entries query
            [{
                "total_matching": 1, "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "by_publication": [], "by_table_scope": [],
                "by_cluster_type": [], "by_growth_phase": [],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "time_course_count": 0,
            }],
            # _run_detail
            [{
                "experiment_id": "e1", "experiment_name": "n", "publication_doi": "d",
                "authors": ["Smith J", "Jones K"],
                "organism_name": "Prochlorococcus MED4",
                "treatment_type": [], "background_factors": [],
                "coculture_partner": None, "omics_type": "RNASEQ",
                "is_time_course": "false",
                "table_scope": None, "table_scope_detail": None,
                "gene_count": 100, "distinct_gene_count": 100,
                "significant_up_count": 0, "significant_down_count": 0,
                "time_point_count": 0, "time_point_labels": [],
                "time_point_orders": [], "time_point_hours": [],
                "time_point_totals": [], "time_point_significant_up": [],
                "time_point_significant_down": [], "time_point_growth_phases": [],
                "clustering_analysis_count": 0, "cluster_types": [],
                "growth_phases": [], "derived_metric_count": 0,
                "derived_metric_value_kinds": [], "compartment": None,
            }],
        ]
        result = list_experiments(conn=mock_conn)
        assert result["results"][0]["authors"] == ["Smith J", "Jones K"]
```

**If the sibling tests in this class use a different mock structure** (e.g., `conftest.py` provides a different fixture name, or stubs use `return_value` not `side_effect`), match the existing pattern. Read 30 lines above and below `class TestListExperiments` first.

- [ ] **Step 2: Run the test to confirm it passes**

(Yes — it should pass already since the api function is verbatim passthrough.)

```bash
uv run pytest tests/unit/test_api_functions.py::TestListExperiments::test_authors_passes_through_from_builder -v
```
Expected: PASS.

If it fails because the fixture pattern doesn't match this class's style, adjust the test to match before proceeding.

---

### Task 9: Document `authors` in api/ docstring

**Files:**
- Modify: [`multiomics_explorer/api/functions.py:867-925`](../../multiomics_explorer/api/functions.py#L867-L925)

- [ ] **Step 1: Update the docstring's per-result field list**

Find the docstring of `def list_experiments` at line 867. Update the compact-fields paragraph. Replace:

```
    Per result (compact): experiment_id, experiment_name, publication_doi,
    organism_name, treatment_type, background_factors, coculture_partner,
```

with:

```
    Per result (compact): experiment_id, experiment_name, publication_doi,
    authors, organism_name, treatment_type, background_factors, coculture_partner,
```

- [ ] **Step 2: Run the api test class to confirm no regressions**

```bash
uv run pytest tests/unit/test_api_functions.py::TestListExperiments -v
```
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_api_functions.py multiomics_explorer/api/functions.py
git commit -m "feat(list_experiments): document authors field in api docstring + add passthrough test

F-AUDIT-4 layer 2 from MCP usability audit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Add `authors` field to MCP wrapper Pydantic — test first

**Files:**
- Modify: [`tests/unit/test_tool_wrappers.py`](../../tests/unit/test_tool_wrappers.py) — `class TestListExperimentsWrapper` (line 2222)

- [ ] **Step 1: Update the `_SAMPLE_EXP` dict to include `authors`**

In `tests/unit/test_tool_wrappers.py` find `_SAMPLE_EXP` at line 2240. Add an `authors` entry before `organism_name`:

```python
    _SAMPLE_EXP = {
        "experiment_id": "test_exp_1",
        "experiment_name": "MED4 Coculture with Alteromonas HOT1A3 (RNASEQ)",
        "publication_doi": "10.1234/test",
        "authors": ["Smith J", "Jones K"],
        "organism_name": "Prochlorococcus MED4",
        ...
    }
```

- [ ] **Step 2: Add a wrapper test to lock `authors` propagation**

Insert this test in `TestListExperimentsWrapper` after `test_detail_mode_has_results` (around line 2293):

```python
    @pytest.mark.asyncio
    async def test_authors_propagates_to_response(self, tool_fns, mock_ctx):
        """authors field from api dict reaches the Pydantic ExperimentResult."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        assert result.results[0].authors == ["Smith J", "Jones K"]
```

- [ ] **Step 3: Run the new test to confirm it fails**

```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestListExperimentsWrapper::test_authors_propagates_to_response -v
```
Expected: FAIL — `ExperimentResult` has no `authors` attribute.

---

### Task 11: Add `authors` to `ExperimentResult` Pydantic model

**Files:**
- Modify: [`multiomics_explorer/mcp_server/tools.py:1750-1773`](../../multiomics_explorer/mcp_server/tools.py#L1750-L1773) — `class ExperimentResult`

- [ ] **Step 1: Add the field to ExperimentResult**

In `tools.py`, locate `class ExperimentResult` at line 1750. Add `authors` immediately after `publication_doi` (line 1754):

```python
        publication_doi: str = Field(description="Publication DOI (e.g. '10.1038/ismej.2016.70')")
        authors: list[str] = Field(default_factory=list, description="Publication authors (e.g. ['Smith J', 'Jones K']). Sourced from Publication.authors via the Has_experiment edge — no need to join with list_publications for author attribution.")
        organism_name: str = Field(description="Profiled organism (e.g. 'Prochlorococcus MED4')")
```

- [ ] **Step 2: Run the new test to confirm it passes**

```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestListExperimentsWrapper::test_authors_propagates_to_response -v
```
Expected: PASS.

- [ ] **Step 3: Run the full wrapper class**

```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestListExperimentsWrapper -v
```
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_tool_wrappers.py multiomics_explorer/mcp_server/tools.py
git commit -m "feat(list_experiments): add authors field to ExperimentResult

F-AUDIT-4 layer 3 from MCP usability audit. Surfaces publication authors
on each experiment row so per-experiment workflows don't need to join
with list_publications.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Update `list_experiments` YAML and regenerate about-content

**Files:**
- Modify: [`multiomics_explorer/inputs/tools/list_experiments.yaml`](../../multiomics_explorer/inputs/tools/list_experiments.yaml)
- Generates: [`multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_experiments.md`](../../multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_experiments.md)

- [ ] **Step 1: Read the existing YAML to find the right insertion point**

```bash
sed -n '1,80p' multiomics_explorer/inputs/tools/list_experiments.yaml
```
Note the structure (examples / mistakes / chaining sections).

- [ ] **Step 2: Add a "no need to join" mistake-style note**

Append to (or insert into) the `mistakes:` section the following bullet:

```yaml
  - "authors is on every result row — no need to join with list_publications when you only need author attribution. list_publications is still the right call for richer publication metadata (abstract, journal, year)."
```

If the YAML has no `mistakes:` section, add one near the top following the gene_overview.yaml pattern.

- [ ] **Step 3: Regenerate about-content for list_experiments**

```bash
uv run python scripts/build_about_content.py list_experiments
```

- [ ] **Step 4: Verify `authors` appears in the regenerated markdown**

```bash
grep -A1 "authors" multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_experiments.md | head -10
```
Expected: see the field in the response-format section.

- [ ] **Step 5: Run the about-content consistency tests**

```bash
uv run pytest tests/unit/test_about_content.py -v
```
Expected: PASS — `expected-keys` block in the about file should now include `authors`.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/inputs/tools/list_experiments.yaml multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_experiments.md
git commit -m "docs(list_experiments): note authors field replaces the list_publications join + regen

F-AUDIT-4 layer 4 from MCP usability audit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Regenerate regression baselines for `list_experiments`

**Files:**
- Updates: [`tests/regression/test_regression/list_experiments_*.yml`](../../tests/regression/test_regression/) (8 baseline files)

The new column `authors` is in every detail-row baseline. Without regen the baseline diffs will fail.

- [ ] **Step 1: Regenerate all list_experiments baselines**

```bash
uv run pytest tests/regression/ -m kg --force-regen -k list_experiments -v
```
Expected: all baselines rewritten; PASS on first regen pass.

- [ ] **Step 2: Verify the regenerated baselines now contain `authors`**

```bash
grep -l "authors:" tests/regression/test_regression/list_experiments_*.yml
```
Expected: every detail-row baseline file (not the `_summary_*.yml` files).

- [ ] **Step 3: Run regression once more without `--force-regen` to confirm clean**

```bash
uv run pytest tests/regression/ -m kg -k list_experiments -v
```
Expected: all PASS.

- [ ] **Step 4: Commit baselines**

```bash
git add tests/regression/test_regression/list_experiments_*.yml
git commit -m "test(regression): regenerate list_experiments baselines for authors field

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Update `CLAUDE.md` if needed

**Files:**
- Modify: [`CLAUDE.md`](../../CLAUDE.md) — only if the row description for `list_experiments` mentions specific fields

- [ ] **Step 1: Check if the CLAUDE.md row mentions the field set**

```bash
grep -A1 "list_experiments" CLAUDE.md | head
```

- [ ] **Step 2: If the row enumerates fields, add `authors`; otherwise skip this task**

If the existing row text mentions specific compact fields, add `authors` to that list; if it's a generic description, no edit needed.

If you edit:

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE): list_experiments — note authors field

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Section 3 — Rubric promotion (item 5)

### Task 15: Add the field-rubric reference under add-or-update-tool skill

**Files:**
- Create: [`.claude/skills/add-or-update-tool/references/field-rubric.md`](../../.claude/skills/add-or-update-tool/references/field-rubric.md)

- [ ] **Step 1: Create the rubric reference file**

Create `.claude/skills/add-or-update-tool/references/field-rubric.md` with this content:

```markdown
# Field-design rubric for tools

This rubric was distilled from the 2026-04-29 MCP usability audit
(`docs/superpowers/specs/2026-04-29-mcp-usability-audit.md`). Apply
when adding a new tool, modifying an existing tool's response schema, or
reviewing a tool change.

A tool's response schema passes the rubric iff:

- [ ] **Field examples are real KG values** — not placeholders, not stubs,
      not "TBD", not known-bad strings. The example a reader sees
      in `Field(description="... (e.g. ...)")` is a *prediction* of what real
      values look like; placeholder examples train the LLM to expect them.
- [ ] **Presence-only fields say so** — and name the drill-down tool that
      surfaces content. `annotation_types` was the canonical anti-example:
      a list of source names that does *not* predict term content
      informativeness, but the original description was silent on the
      limitation.
- [ ] **Coarse-summary fields signpost the drill-down tool by name** in the
      field description. The DM fields on `gene_overview` show the model:
      `"Use to route to genes_by_{kind}_metric drill-downs"`.
- [ ] **Tool docstring includes downstream direction** — "after this, drill
      into Y to get Z" — not just upstream callers ("use after X"). Pattern
      model: `gene_details` docstring naming `list_organisms`,
      `gene_homologs`, `gene_ontology_terms` for the relevant axes.
- [ ] **Response rows are typed Pydantic models** — not `list[dict]` —
      whenever the row shape is known. Untyped dict erodes self-
      documentation; the LLM can only discover field names by sampling.
- [ ] **Empty-result shapes are unambiguous** — `not_found` ≠ `not_matched`
      ≠ `no_groups` ≠ `out_of_pipeline_scope`, and each is documented in
      the envelope schema. When two zero-row outcomes have different
      meaning, surface the distinction structurally.
- [ ] **Field name predicts shape** — `gene_count` should describe a count
      of genes; if the field is a row count summed across timepoints,
      name it `cumulative_row_count`. Misleading names need explicit
      description disclaimers.
- [ ] **No Cypher-syntax jargon** in user-facing descriptions — `g{.*}`,
      APOC function names, etc. belong in builder docstrings, not in
      Pydantic field text.

When applying the rubric to an existing tool, run a local audit against
its Pydantic model + docstring and file a separate spec for any failing
clauses; do not bundle rubric-driven cleanup into unrelated tool work.
```

- [ ] **Step 2: Add a reference link from the skill's SKILL.md**

In `.claude/skills/add-or-update-tool/SKILL.md`, find the top of the file (after the frontmatter, near line 8 — the first paragraph that links to the checklist). Replace:

```markdown
See [checklist](references/checklist.md) for templates and file paths.
See the **testing** skill for per-layer test patterns and fixtures.
```

with:

```markdown
See [checklist](references/checklist.md) for templates and file paths.
See [field-rubric](references/field-rubric.md) for response-schema
quality criteria — apply on every new tool and every response-schema
change.
See the **testing** skill for per-layer test patterns and fixtures.
```

- [ ] **Step 3: Confirm the file exists and is well-formed**

```bash
test -f .claude/skills/add-or-update-tool/references/field-rubric.md && echo OK
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/add-or-update-tool/references/field-rubric.md .claude/skills/add-or-update-tool/SKILL.md
git commit -m "docs(skill): promote MCP-audit field rubric into add-or-update-tool

Item 5 of MCP Pass A. The 8-clause rubric was the cross-cutting output
of the 2026-04-29 audit; promoting it to the skill makes it the gate
on future tool changes so audit lessons compound.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Section 4 — Final verification

### Task 16: Run the full test suites

**Files:** none (verification only)

- [ ] **Step 1: Unit tests**

```bash
uv run pytest tests/unit/ -v
```
Expected: all PASS.

- [ ] **Step 2: Integration tests (requires KG)**

```bash
uv run pytest tests/integration/ -v -m kg
```
Expected: all PASS.

- [ ] **Step 3: Regression tests (requires KG)**

```bash
uv run pytest tests/regression/ -m kg
```
Expected: all PASS.

- [ ] **Step 4: Confirm clean working tree**

```bash
git status
```
Expected: `nothing to commit, working tree clean`.

- [ ] **Step 5: Inspect commit log to verify all task commits landed**

```bash
git log --oneline main..HEAD
```
Expected: 9-13 commits matching the per-task commit messages above.

---

### Task 17: Push branch and open PR (user-gated)

**Files:** none (git only)

This task requires explicit user approval before running. Don't push or open a PR unless the user asks for it.

- [ ] **Step 1: Wait for user approval**

Confirm with the user before running `git push` or `gh pr create`.

- [ ] **Step 2 (after approval): Push branch**

```bash
git push -u origin feat/mcp-pass-a-paper-cuts
```

- [ ] **Step 3 (after approval): Open PR**

```bash
gh pr create --title "feat: MCP Pass A paper-cuts (audit findings 1, 2L1, 3, authors, rubric)" --body "$(cat <<'EOF'
## Summary

Pass A paper-cuts from the 2026-04-29 MCP usability audit.
Source: docs/superpowers/specs/2026-04-29-mcp-usability-audit.md
Plan: docs/superpowers/plans/2026-04-30-mcp-pass-a-paper-cuts.md

- F-AUDIT-1: replace 'Alternative locus ID' placeholder in gene_overview Pydantic field examples
- F-AUDIT-2 layer 1: tighten annotation_types description (presence-only, points to gene_ontology_terms)
- F-AUDIT-3a: add downstream drill-down clauses to gene_overview summary fields
- F-AUDIT-3b: add downstream-direction trailers to 6 summary tools' docstrings
- list_experiments.authors: surface Publication.authors on each row (saves a list_publications join)
- Rubric: promote 8-clause field-design rubric into add-or-update-tool skill

All five items are independent of pending KG-side decisions — Passes B/C/D
wait for the KG round-trip per the audit triage.

## Test plan

- [x] tests/unit/ pass
- [x] tests/integration/ pass (KG up)
- [x] tests/regression/ pass after baseline regen for list_experiments

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

**Spec coverage check:**
- F-AUDIT-1 → Task 1 ✓
- F-AUDIT-2 layer 1 → Task 2 ✓
- F-AUDIT-3a (gene_overview field clauses) → Task 3 ✓
- F-AUDIT-3b (six summary-tool docstring trailers) → Task 4 ✓
- About-content regeneration → Task 5 ✓
- list_experiments.authors (4-layer pass) → Tasks 6-13 ✓
- CLAUDE.md doc update → Task 14 (conditional) ✓
- Rubric promotion → Task 15 ✓
- Final verification → Task 16 ✓
- PR (user-gated) → Task 17 ✓

**Type/name consistency:** `authors: list[str]` is used consistently across builder RETURN (`coalesce(p.authors, [])`), api docstring, Pydantic field, test fixtures, and regression baselines. Pattern matches `background_factors: list[str]` already in the same model.

**Coverage of layer-rules:** Doc-only items touch only Layer 3 (`mcp_server/tools.py`) + Layer 4 (skills regen). The `authors` item touches all four layers as required for behavioral changes. Tests run at every layer's gate.

**Risks:**
- Task 8's mock-fixture pattern may differ from the rest of the file — the step explicitly directs the implementer to read sibling tests first. If conftest provides a different fixture name, adapt to the existing style.
- Regression baseline regen (Task 13) is the only `--force-regen` run; the regen affects 6 detail-row YAMLs only (`_summary_*.yml` files don't carry per-row `authors`).
- Each commit is independent and can be cherry-picked; if any test gate fails mid-way, the previous tasks are still valid commits.

**Open question for the implementer:** if any sibling tool's docstring (Task 4 steps 2/4/5/6) already has a downstream-direction trailer (it shouldn't, but the audit only sampled a few), preserve the existing trailer and merge with the new one rather than replacing.
