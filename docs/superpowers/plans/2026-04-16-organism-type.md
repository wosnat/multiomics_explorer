# Organism Type Property Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose `organism_type`, `reference_database`, and `reference_proteome` from OrganismTaxon nodes in the `list_organisms` tool output, with a `by_organism_type` summary breakdown.

**Architecture:** Query builder adds 3 columns. API layer sparse-strips reference fields when null and builds a `by_organism_type` summary. MCP layer adds model fields. Docs updated. Regression fixtures regenerated.

**Tech Stack:** Python, Neo4j (Cypher), FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-04-16-organism-type-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `multiomics_explorer/kg/queries_lib.py` | Modify | Add 3 columns to `build_list_organisms` RETURN |
| `multiomics_explorer/api/functions.py` | Modify | Sparse-strip reference fields, build `by_organism_type` |
| `multiomics_explorer/mcp_server/tools.py` | Modify | Add fields to `OrganismResult`, add `OrgTypeBreakdown`, update `ListOrganismsResponse`, update docstring |
| `tests/unit/test_query_builders.py` | Modify | Test new columns in builder |
| `tests/unit/test_tool_correctness.py` | Modify | Test `organism_type` in results, sparse fields, `by_organism_type` |
| `multiomics_explorer/inputs/tools/list_organisms.yaml` | Modify | Document new output fields |
| `tests/regression/` | Regenerate | Golden files pick up new columns + organism renames |

---

### Task 1: Query builder — add columns

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:895-939`
- Test: `tests/unit/test_query_builders.py:810-854`

- [ ] **Step 1: Write failing test**

In `tests/unit/test_query_builders.py`, add to `TestBuildListOrganisms` (after `test_ordered_by_genus_and_name`):

```python
    def test_returns_organism_type(self):
        cypher, _ = build_list_organisms()
        assert "o.organism_type AS organism_type" in cypher

    def test_returns_reference_fields(self):
        cypher, _ = build_list_organisms()
        assert "o.reference_database AS reference_database" in cypher
        assert "o.reference_proteome AS reference_proteome" in cypher
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListOrganisms::test_returns_organism_type -v`
Expected: FAIL — `organism_type` not in cypher.

- [ ] **Step 3: Update `build_list_organisms`**

In `multiomics_explorer/kg/queries_lib.py:920-938`, change:

```python
    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        "RETURN o.preferred_name AS organism_name,\n"
        "       o.genus AS genus,\n"
        "       o.species AS species,\n"
        "       o.strain_name AS strain,\n"
        "       o.clade AS clade,\n"
        "       o.ncbi_taxon_id AS ncbi_taxon_id,\n"
        "       o.gene_count AS gene_count,\n"
        "       o.publication_count AS publication_count,\n"
        "       o.experiment_count AS experiment_count,\n"
        "       o.treatment_types AS treatment_types,\n"
        "       coalesce(o.background_factors, []) AS background_factors,\n"
        "       o.omics_types AS omics_types,\n"
        "       coalesce(o.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
        "       coalesce(o.cluster_types, []) AS cluster_types"
        f"{verbose_cols}\n"
        "ORDER BY o.genus, o.preferred_name"
    )
```

to:

```python
    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        "RETURN o.preferred_name AS organism_name,\n"
        "       o.organism_type AS organism_type,\n"
        "       o.genus AS genus,\n"
        "       o.species AS species,\n"
        "       o.strain_name AS strain,\n"
        "       o.clade AS clade,\n"
        "       o.ncbi_taxon_id AS ncbi_taxon_id,\n"
        "       o.gene_count AS gene_count,\n"
        "       o.publication_count AS publication_count,\n"
        "       o.experiment_count AS experiment_count,\n"
        "       o.treatment_types AS treatment_types,\n"
        "       coalesce(o.background_factors, []) AS background_factors,\n"
        "       o.omics_types AS omics_types,\n"
        "       coalesce(o.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
        "       coalesce(o.cluster_types, []) AS cluster_types,\n"
        "       o.reference_database AS reference_database,\n"
        "       o.reference_proteome AS reference_proteome"
        f"{verbose_cols}\n"
        "ORDER BY o.genus, o.preferred_name"
    )
```

Update the docstring RETURN keys to include `organism_type, reference_database, reference_proteome`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListOrganisms -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add organism_type and reference fields to build_list_organisms"
```

---

### Task 2: API layer — sparse stripping + `by_organism_type`

**Files:**
- Modify: `multiomics_explorer/api/functions.py:552-597`

- [ ] **Step 1: Update `list_organisms`**

In `multiomics_explorer/api/functions.py:552-597`, change the function body. After the pagination slice (line 580) and before the verbose gate (line 583), add sparse stripping:

```python
    results = all_results[offset:offset + limit] if limit else all_results[offset:]

    # Sparse-strip reference fields when null
    for r in results:
        if r.get("reference_database") is None:
            r.pop("reference_database", None)
            r.pop("reference_proteome", None)
```

After the existing `ct_counts` block (lines 574-578), add `by_organism_type`:

```python
    # Compute by_organism_type breakdown from all results
    ot_counts: dict[str, int] = {}
    for org in all_results:
        ot = org.get("organism_type")
        if ot:
            ot_counts[ot] = ot_counts.get(ot, 0) + 1
```

In the return dict (line 586), add `by_organism_type` after `by_cluster_type`:

```python
        "by_organism_type": sorted(
            [{"organism_type": k, "count": v} for k, v in ot_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        ),
```

Update the docstring to mention `organism_type`, `reference_database`, `reference_proteome`, `by_organism_type`.

- [ ] **Step 2: Run existing unit tests to verify no regressions**

Run: `pytest tests/unit/test_tool_correctness.py::TestListOrganismsCorrectness -v`
Expected: PASS (existing tests don't check new fields, so no breakage)

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/api/functions.py
git commit -m "feat: add organism_type summary and sparse reference fields to list_organisms API"
```

---

### Task 3: MCP model + docstring

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py:339-419`
- Test: `tests/unit/test_tool_correctness.py:1716-1754`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_tool_correctness.py`, add to `TestListOrganismsCorrectness`:

```python
    @pytest.mark.asyncio
    async def test_organism_type_in_results(self, tool_fns, mock_ctx):
        """Results include organism_type field."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 2,
                "returned": 2,
                "truncated": False,
                "by_cluster_type": [],
                "by_organism_type": [
                    {"organism_type": "genome_strain", "count": 1},
                    {"organism_type": "reference_proteome_match", "count": 1},
                ],
                "results": [
                    {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain",
                     "genus": "Prochlorococcus", "species": "Prochlorococcus marinus",
                     "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919,
                     "gene_count": 1976, "publication_count": 11, "experiment_count": 46,
                     "treatment_types": ["coculture"], "background_factors": [],
                     "omics_types": ["RNASEQ"]},
                    {"organism_name": "Alteromonas (MarRef v6)",
                     "organism_type": "reference_proteome_match",
                     "genus": "Alteromonas", "species": None, "strain": "Alt_MarRef",
                     "clade": None, "ncbi_taxon_id": 232, "gene_count": 500,
                     "publication_count": 1, "experiment_count": 3,
                     "treatment_types": ["coculture"], "background_factors": [],
                     "omics_types": ["PROTEOMICS"],
                     "reference_database": "MarRef v6",
                     "reference_proteome": "GCA_003513035.1"},
                ],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)

        assert result.results[0].organism_type == "genome_strain"
        assert result.results[0].reference_database is None
        assert result.results[0].reference_proteome is None
        assert result.results[1].organism_type == "reference_proteome_match"
        assert result.results[1].reference_database == "MarRef v6"
        assert result.results[1].reference_proteome == "GCA_003513035.1"

    @pytest.mark.asyncio
    async def test_by_organism_type_in_envelope(self, tool_fns, mock_ctx):
        """Envelope includes by_organism_type breakdown."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 2,
                "returned": 2,
                "truncated": False,
                "by_cluster_type": [],
                "by_organism_type": [
                    {"organism_type": "genome_strain", "count": 25},
                    {"organism_type": "treatment", "count": 5},
                    {"organism_type": "reference_proteome_match", "count": 2},
                ],
                "results": [
                    {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain",
                     "genus": "Prochlorococcus", "species": "Prochlorococcus marinus",
                     "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919,
                     "gene_count": 1976, "publication_count": 11, "experiment_count": 46,
                     "treatment_types": [], "background_factors": [], "omics_types": []},
                    {"organism_name": "Test Org", "organism_type": "treatment",
                     "genus": "Test", "species": None, "strain": None, "clade": None,
                     "ncbi_taxon_id": None, "gene_count": 0, "publication_count": 0,
                     "experiment_count": 0,
                     "treatment_types": [], "background_factors": [], "omics_types": []},
                ],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)

        assert len(result.by_organism_type) == 3
        assert result.by_organism_type[0].organism_type == "genome_strain"
        assert result.by_organism_type[0].count == 25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tool_correctness.py::TestListOrganismsCorrectness::test_organism_type_in_results -v`
Expected: FAIL — `OrganismResult` has no `organism_type` field.

- [ ] **Step 3: Update `OrganismResult` model**

In `multiomics_explorer/mcp_server/tools.py:339-362`, after `organism_name` (line 340), add:

```python
        organism_type: str = Field(description="Classification: 'genome_strain', 'treatment', or 'reference_proteome_match'")
```

After `cluster_count` (line 362), add:

```python
        # sparse reference fields (reference_proteome_match only)
        reference_database: str | None = Field(default=None, description="Reference database used for matching (e.g. 'MarRef v6'). Only on reference_proteome_match organisms.")
        reference_proteome: str | None = Field(default=None, description="Accession of matched reference proteome (e.g. 'GCA_003513035.1'). Only on reference_proteome_match organisms.")
```

- [ ] **Step 4: Add `OrgTypeBreakdown` model and update `ListOrganismsResponse`**

In `multiomics_explorer/mcp_server/tools.py`, after `OrgClusterTypeBreakdown` (line 366), add:

```python
    class OrgTypeBreakdown(BaseModel):
        organism_type: str = Field(description="Organism type (e.g. 'genome_strain')")
        count: int = Field(description="Number of organisms of this type (e.g. 25)")
```

In `ListOrganismsResponse` (line 368-374), after `by_cluster_type` (line 370), add:

```python
        by_organism_type: list[OrgTypeBreakdown] = Field(default_factory=list, description="Organism counts per type, sorted by count descending")
```

- [ ] **Step 5: Update tool function body**

In `multiomics_explorer/mcp_server/tools.py:404-414`, after the `by_cluster_type` construction (line 406), add:

```python
            by_organism_type = [OrgTypeBreakdown(**b) for b in result.get("by_organism_type", [])]
```

Update the `ListOrganismsResponse` construction (line 407-414) to include:

```python
            response = ListOrganismsResponse(
                total_entries=result["total_entries"],
                by_cluster_type=by_cluster_type,
                by_organism_type=by_organism_type,
                returned=result["returned"],
                offset=result.get("offset", 0),
                truncated=result["truncated"],
                results=organisms,
            )
```

- [ ] **Step 6: Update tool docstring**

Change the docstring at line 393-399 to:

```python
        """List all organisms in the knowledge graph.

        Returns taxonomy, gene counts, publication counts, and organism_type
        for each organism. organism_type classifies each organism as
        'genome_strain', 'treatment', or 'reference_proteome_match'.
        Reference proteome match organisms also include reference_database
        and reference_proteome fields.

        Use the returned organism names as filter values in genes_by_function,
        resolve_gene, genes_by_ontology, list_publications, etc. The organism
        filter uses partial matching — "MED4", "Prochlorococcus MED4", and
        "Prochlorococcus" all work.
        """
```

- [ ] **Step 7: Update existing test to include `organism_type`**

In `tests/unit/test_tool_correctness.py:1720-1754`, the existing `test_returns_organisms` mock data doesn't include `organism_type`. Update both mock result dicts to include it:

```python
                    {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain",
                     "genus": "Prochlorococcus",
```

```python
                    {"organism_name": "Alteromonas macleodii EZ55", "organism_type": "genome_strain",
                     "genus": "Alteromonas",
```

Also add `"by_organism_type": []` and `"by_cluster_type": []` to the mock return value.

- [ ] **Step 8: Run tests**

Run: `pytest tests/unit/test_tool_correctness.py::TestListOrganismsCorrectness -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_correctness.py
git commit -m "feat: add organism_type, reference fields, and by_organism_type to list_organisms MCP"
```

---

### Task 4: Documentation — YAML + regenerate

**Files:**
- Modify: `multiomics_explorer/inputs/tools/list_organisms.yaml`

- [ ] **Step 1: Update YAML**

In `multiomics_explorer/inputs/tools/list_organisms.yaml`, update the first example response to include `organism_type` and update the example to show a reference_proteome_match organism:

```yaml
examples:
  - title: Browse all organisms
    call: list_organisms()
    response: |
      {
        "total_entries": 32,
        "by_organism_type": [
          {"organism_type": "genome_strain", "count": 25},
          {"organism_type": "treatment", "count": 5},
          {"organism_type": "reference_proteome_match", "count": 2}
        ],
        "returned": 5,
        "truncated": true,
        "offset": 0,
        "results": [
          {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain", "genus": "Prochlorococcus", "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 11, "experiment_count": 46, "treatment_types": ["coculture", "carbon_stress", "salt_stress", "viral", ...], "omics_types": ["RNASEQ", "MICROARRAY", "PROTEOMICS"], "clustering_analysis_count": 4, "cluster_types": ["condition_comparison", "diel", "classification"]},
          {"organism_name": "Alteromonas (MarRef v6)", "organism_type": "reference_proteome_match", "genus": "Alteromonas", "gene_count": 500, "reference_database": "MarRef v6", "reference_proteome": "GCA_003513035.1", ...}
        ]
      }
```

Add a mistakes entry:

```yaml
  - "reference_database and reference_proteome are sparse — only present on reference_proteome_match organisms, absent from others"
  - "organism_type values: 'genome_strain' (real genome assembly), 'treatment' (non-genomic coculture partners), 'reference_proteome_match' (identified via reference database matching)"
```

- [ ] **Step 2: Regenerate MCP resource markdown**

Run: `uv run python scripts/build_about_content.py`

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/inputs/tools/list_organisms.yaml multiomics_explorer/skills/
git commit -m "docs: update list_organisms YAML and regenerate MCP resource docs"
```

---

### Task 5: Regression fixtures

**Files:**
- Regenerate: `tests/regression/test_regression/list_organisms.yml`
- Regenerate: `tests/regression/test_regression/list_organisms_raw.yml`

- [ ] **Step 1: Regenerate fixtures**

Run: `pytest -m kg tests/regression/test_regression.py --force-regen -v`

This regenerates all golden files, picking up the new columns (`organism_type`, `reference_database`, `reference_proteome`) and the organism renames.

- [ ] **Step 2: Verify regression tests pass**

Run: `pytest -m kg tests/regression/test_regression.py -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/regression/
git commit -m "test: regenerate regression fixtures for organism_type and renames"
```

---

### Task 6: Smoke test

- [ ] **Step 1: Run full unit test suite**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Run integration tests**

Run: `pytest -m kg -v`
Expected: All PASS

- [ ] **Step 3: Restart MCP and smoke test**

Run `/mcp` to restart the MCP server, then test:

```
list_organisms(limit=3)
```

Verify: `organism_type` appears on every result, `reference_database`/`reference_proteome` appear only on reference_proteome_match organisms, `by_organism_type` appears in envelope.
