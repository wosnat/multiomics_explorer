# gene_response_profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `gene_response_profile` MCP tool that summarizes a gene's expression response across all experiments, plus expose `rank_up`/`rank_down` fields in `differential_expression_by_gene`.

**Architecture:** Two-query tool (Q1 envelope + Q2 two-pass aggregation with Cypher-side pagination). Follows existing 4-layer pattern: query builder → API function → MCP wrapper → about content. The `differential_expression_by_gene` update is a small additive change across all layers.

**Tech Stack:** Python, Neo4j/Cypher, Pydantic, FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-03-31-gene-response-profile-design.md`

---

### Task 1: Schema baseline + DE by gene rank fields (query builder)

**Files:**
- Modify: `multiomics_explorer/config/schema_baseline.yaml`
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Regenerate schema baseline from live KG**

The KG already has `rank_up`/`rank_down` on edges. Regenerate the baseline to pick them up:

```bash
uv run python -c "
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.schema import load_schema_from_neo4j, save_baseline
conn = GraphConnection()
schema = load_schema_from_neo4j(conn)
path = save_baseline(schema)
print(f'Saved to {path}')
conn.close()
"
```

Verify `rank_up` and `rank_down` appear in `multiomics_explorer/config/schema_baseline.yaml` under `Changes_expression_of.properties`.

- [ ] **Step 2: Write failing test for rank fields in DE by gene query builder**

In `tests/unit/test_query_builders.py`, add to `TestBuildDifferentialExpressionByGene` class (or create it if the detail builder tests are in `TestBuildDifferentialExpressionByGeneSummaryGlobal`):

```python
class TestBuildDifferentialExpressionByGene:
    def test_returns_rank_up_rank_down(self):
        """Detail query includes directional rank columns."""
        cypher, _ = build_differential_expression_by_gene()
        assert "rank_up" in cypher
        assert "rank_down" in cypher
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_query_builders.py::TestBuildDifferentialExpressionByGene::test_returns_rank_up_rank_down -v`
Expected: FAIL — `rank_up` not in cypher

- [ ] **Step 4: Add rank_up/rank_down to RETURN clause**

In `multiomics_explorer/kg/queries_lib.py`, in `build_differential_expression_by_gene`, add two lines to the RETURN clause after `r.rank_by_effect AS rank`:

```python
        "       r.rank_by_effect AS rank,\n"
        "       r.rank_up AS rank_up,\n"
        "       r.rank_down AS rank_down,\n"
        "       r.expression_status AS expression_status"
```

Update the docstring RETURN keys to include `rank_up, rank_down` (compact now has 13 keys).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_query_builders.py::TestBuildDifferentialExpressionByGene::test_returns_rank_up_rank_down -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/config/schema_baseline.yaml multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(kg): add rank_up/rank_down to schema baseline and DE by gene query builder"
```

---

### Task 2: DE by gene MCP model + about content update

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Modify: `multiomics_explorer/inputs/tools/differential_expression_by_gene.yaml`
- Test: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Add rank_up/rank_down to ExpressionRow Pydantic model**

In `multiomics_explorer/mcp_server/tools.py`, add two fields to the `ExpressionRow` class after the `rank` field:

```python
        rank_up: int | None = Field(
            default=None,
            description="Rank by |log2FC| among significant_up genes"
            " within experiment x timepoint."
            " Null if not significant_up. 1 = strongest.",
        )
        rank_down: int | None = Field(
            default=None,
            description="Rank by |log2FC| among significant_down genes"
            " within experiment x timepoint."
            " Null if not significant_down. 1 = strongest.",
        )
```

- [ ] **Step 2: Run existing DE by gene wrapper tests**

Run: `pytest tests/unit/test_tool_wrappers.py::TestDifferentialExpressionByGeneWrapper -v`
Expected: PASS (new fields have defaults, so existing mocked data still works)

- [ ] **Step 3: Update API contract expected keys**

In `tests/integration/test_api_contract.py`, in `TestDifferentialExpressionByGeneContract::test_result_row_keys`, add `"rank_up"` and `"rank_down"` to `expected_compact`:

```python
        expected_compact = {
            "locus_tag", "gene_name", "experiment_id", "treatment_type",
            "timepoint", "timepoint_hours", "timepoint_order",
            "log2fc", "padj", "rank", "rank_up", "rank_down",
            "expression_status",
        }
```

- [ ] **Step 4: Update about YAML**

In `multiomics_explorer/inputs/tools/differential_expression_by_gene.yaml`, the `rank_up` and `rank_down` fields are not verbose-only — they're compact fields (always present). No change to `verbose_fields` list. Update any example response JSON that shows result rows to include `"rank_up": null, "rank_down": null` (or with values for significant genes).

- [ ] **Step 5: Rebuild about content**

Run: `uv run python scripts/build_about_content.py differential_expression_by_gene`

- [ ] **Step 6: Run about content tests**

Run: `pytest tests/unit/test_about_content.py -v -k differential_expression_by_gene`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/integration/test_api_contract.py multiomics_explorer/inputs/tools/differential_expression_by_gene.yaml multiomics_explorer/skills/
git commit -m "feat(mcp): add rank_up/rank_down to ExpressionRow model and about content"
```

---

### Task 3: gene_response_profile envelope query builder

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_query_builders.py`, add import for the new builder (will fail until implemented), then add test class:

```python
from multiomics_explorer.kg.queries_lib import (
    # ... existing imports ...
    build_gene_response_profile_envelope,
)


class TestBuildGeneResponseProfileEnvelope:
    def test_basic(self):
        """Envelope query with required params."""
        cypher, params = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"],
        )
        assert "MATCH" in cypher
        assert params["locus_tags"] == ["PMM0370"]

    def test_returns_expected_columns(self):
        """All RETURN aliases present."""
        cypher, _ = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"],
        )
        for col in [
            "found_genes", "organism_name", "has_expression",
            "has_significant",
        ]:
            assert col in cypher

    def test_organism_filter(self):
        cypher, params = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism="MED4",
        )
        assert "toLower($organism)" in cypher
        assert params["organism"] == "MED4"

    def test_treatment_types_filter(self):
        cypher, params = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"],
            treatment_types=["nitrogen_stress"],
        )
        assert "$treatment_types" in cypher
        assert params["treatment_types"] == ["nitrogen_stress"]

    def test_experiment_ids_filter(self):
        cypher, params = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"],
            experiment_ids=["exp1"],
        )
        assert "e.id IN $experiment_ids" in cypher
        assert params["experiment_ids"] == ["exp1"]

    def test_group_by_treatment_type(self):
        cypher, _ = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"],
            group_by="treatment_type",
        )
        assert "e.treatment_type" in cypher

    def test_group_by_experiment(self):
        cypher, _ = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"],
            group_by="experiment",
        )
        assert "e.id" in cypher

    def test_invalid_group_by_raises(self):
        with pytest.raises(ValueError, match="group_by"):
            build_gene_response_profile_envelope(
                locus_tags=["PMM0370"],
                group_by="invalid",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneResponseProfileEnvelope -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement the shared WHERE helper and envelope builder**

In `multiomics_explorer/kg/queries_lib.py`, first add the shared WHERE helper (used by both envelope and aggregation builders):

```python
def _gene_response_profile_where(
    *,
    organism: str | None = None,
    treatment_types: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    experiment_alias: str = "e",
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by gene_response_profile builders.

    experiment_alias allows reuse with different MATCH variable names
    (e.g. 'e' vs 'e2' in the envelope query's group_totals section).
    """
    conditions: list[str] = []
    params: dict = {}
    if organism:
        conditions.append(
            f"ALL(word IN split(toLower($organism), ' ')"
            f" WHERE toLower({experiment_alias}.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if treatment_types:
        conditions.append(
            f"toLower({experiment_alias}.treatment_type) IN $treatment_types"
        )
        params["treatment_types"] = [t.lower() for t in treatment_types]
    if experiment_ids:
        conditions.append(f"{experiment_alias}.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    return conditions, params


def _group_key_expr(group_by: str, alias: str = "e") -> str:
    """Return the Cypher expression for the group key."""
    if group_by == "treatment_type":
        return f"{alias}.treatment_type"
    elif group_by == "experiment":
        return f"{alias}.id"
    else:
        raise ValueError(
            f"group_by must be 'treatment_type' or 'experiment', got '{group_by}'"
        )
```

Then the envelope builder:

```python
def build_gene_response_profile_envelope(
    *,
    locus_tags: list[str],
    organism: str | None = None,
    treatment_types: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
) -> tuple[str, dict]:
    """Build envelope query for gene_response_profile.

    Returns per-gene existence/expression flags and per-group totals
    (experiment count, timepoint count) for the organism.

    RETURN keys: found_genes (list), organism_name, has_expression
    (list of locus_tags), has_significant (list), group_totals (list of
    {group_key, experiments, timepoints}).
    """
    gk = _group_key_expr(group_by)
    gk2 = _group_key_expr(group_by, alias="e2")

    # Conditions for the gene-expression MATCH (alias 'e')
    conditions_e, params = _gene_response_profile_where(
        organism=organism, treatment_types=treatment_types,
        experiment_ids=experiment_ids, experiment_alias="e",
    )
    params["locus_tags"] = locus_tags
    where_e = (
        " AND " + " AND ".join(conditions_e) if conditions_e else ""
    )

    # Same conditions for the group-totals MATCH (alias 'e2')
    conditions_e2, _ = _gene_response_profile_where(
        organism=organism, treatment_types=treatment_types,
        experiment_ids=experiment_ids, experiment_alias="e2",
    )
    where_e2 = (
        " AND " + " AND ".join(conditions_e2) if conditions_e2 else ""
    )

    cypher = (
        # Part 1: Find which input genes exist
        "MATCH (g:Gene)\n"
        "WHERE g.locus_tag IN $locus_tags\n"
        "WITH collect(g.locus_tag) AS found_genes\n"
        "\n"
        # Part 2: For found genes, check expression edges
        "OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g2:Gene)\n"
        f"WHERE g2.locus_tag IN found_genes{where_e}\n"
        "WITH found_genes,\n"
        "     collect(DISTINCT g2.locus_tag) AS has_expression,\n"
        "     collect(DISTINCT CASE WHEN r.expression_status IN"
        " ['significant_up', 'significant_down']"
        " THEN g2.locus_tag END) AS has_significant,\n"
        "     collect(DISTINCT e.organism_name) AS organism_names\n"
        "\n"
        # Part 3: Group totals — experiments and timepoints per group
        "OPTIONAL MATCH (e2:Experiment)-[:Changes_expression_of]->(:Gene)\n"
        f"WHERE e2.organism_name IN organism_names{where_e2}\n"
        f"WITH found_genes, has_expression, has_significant, organism_names,\n"
        f"     {gk2} AS group_key,\n"
        "     collect(DISTINCT e2) AS group_experiments\n"
        "WITH found_genes, has_expression, has_significant,\n"
        "     organism_names[0] AS organism_name,\n"
        "     collect({group_key: group_key,"
        " experiments: size(group_experiments),"
        " timepoints: reduce(s = 0, exp IN group_experiments |"
        " s + COALESCE(exp.time_point_count, 1))}) AS group_totals\n"
        "RETURN found_genes, organism_name,"
        " has_expression, has_significant, group_totals"
    )
    return cypher, params
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneResponseProfileEnvelope -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(kg): add gene_response_profile envelope query builder"
```

---

### Task 4: gene_response_profile aggregation query builder

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_query_builders.py`, add import and test class:

```python
from multiomics_explorer.kg.queries_lib import (
    # ... existing imports ...
    build_gene_response_profile,
)


class TestBuildGeneResponseProfile:
    def test_basic(self):
        """Aggregation query with required params."""
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"],
        )
        assert "MATCH" in cypher
        assert params["locus_tags"] == ["PMM0370"]

    def test_returns_expected_columns(self):
        """All RETURN aliases present."""
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0370"],
        )
        for col in [
            "locus_tag", "gene_name", "product", "gene_category",
            "group_key", "experiments_tested", "experiments_up",
            "experiments_down", "timepoints_tested", "timepoints_up",
            "timepoints_down", "rank_ups", "rank_downs",
            "log2fcs_up", "log2fcs_down",
        ]:
            assert col in cypher

    def test_order_by(self):
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0370"],
        )
        assert "ORDER BY" in cypher
        assert "groups_responded DESC" in cypher

    def test_skip_limit(self):
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"], limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["offset"] == 5
        assert params["limit"] == 10

    def test_group_by_treatment_type(self):
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0370"],
            group_by="treatment_type",
        )
        assert "e.treatment_type" in cypher

    def test_group_by_experiment(self):
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0370"],
            group_by="experiment",
        )
        # group key should use e.id
        assert "e.id AS group_key" in cypher or "e.id" in cypher

    def test_treatment_types_filter(self):
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"],
            treatment_types=["nitrogen_stress"],
        )
        assert "$treatment_types" in cypher
        assert params["treatment_types"] == ["nitrogen_stress"]

    def test_experiment_ids_filter(self):
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"],
            experiment_ids=["exp1"],
        )
        assert "e.id IN $experiment_ids" in cypher
        assert params["experiment_ids"] == ["exp1"]

    def test_invalid_group_by_raises(self):
        with pytest.raises(ValueError, match="group_by"):
            build_gene_response_profile(
                locus_tags=["PMM0370"],
                group_by="invalid",
            )

    def test_no_limit_no_skip(self):
        """Without limit, no SKIP/LIMIT in Cypher."""
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"],
        )
        assert "SKIP" not in cypher
        assert "LIMIT" not in cypher
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneResponseProfile -v`
Expected: FAIL — import error

- [ ] **Step 3: Implement the aggregation builder**

Uses `_gene_response_profile_where` and `_group_key_expr` helpers already added in Task 3.

In `multiomics_explorer/kg/queries_lib.py`, add:

```python
def build_gene_response_profile(
    *,
    locus_tags: list[str],
    organism: str | None = None,
    treatment_types: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build two-pass aggregation query for gene_response_profile.

    Pass 1: compute per-gene sort keys (breadth/depth/timepoints),
    sort and paginate on the gene axis.
    Pass 2: group by experiment first (to compute experiments_up/down),
    then flatten edges for rank/log2fc lists.

    Verified against live KG 2026-03-31.

    RETURN keys: locus_tag, gene_name, product, gene_category,
    group_key, experiments_tested, experiments_up, experiments_down,
    timepoints_tested, timepoints_up, timepoints_down,
    rank_ups (list), rank_downs (list),
    log2fcs_up (list), log2fcs_down (list).
    """
    gk = _group_key_expr(group_by)

    conditions, params = _gene_response_profile_where(
        organism=organism, treatment_types=treatment_types,
        experiment_ids=experiment_ids,
    )
    params["locus_tags"] = locus_tags

    conditions.append("g.locus_tag IN $locus_tags")
    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    # Pass 2 WHERE: same filters minus locus_tags (already scoped by WITH g)
    pass2_conditions, _ = _gene_response_profile_where(
        organism=organism, treatment_types=treatment_types,
        experiment_ids=experiment_ids,
    )
    pass2_where = (
        "WHERE " + " AND ".join(pass2_conditions) + "\n"
        if pass2_conditions else ""
    )

    pagination = ""
    if offset:
        pagination += "\nSKIP $offset"
        params["offset"] = offset
    if limit is not None:
        pagination += "\nLIMIT $limit"
        params["limit"] = limit

    cypher = (
        # Pass 1: sort keys + paginate
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        "WITH g,\n"
        "     count(DISTINCT CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        f" THEN {gk} END) AS groups_responded,\n"
        "     count(DISTINCT CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        " THEN e.id END) AS experiments_responded,\n"
        "     sum(CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        " THEN 1 ELSE 0 END) AS timepoints_responded\n"
        "ORDER BY groups_responded DESC,"
        " experiments_responded DESC,"
        " timepoints_responded DESC,"
        " g.locus_tag ASC"
        f"{pagination}\n"
        "\n"
        # Pass 2: group by experiment first, then aggregate per group
        "WITH g\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{pass2_where}"
        # Intermediate: per gene x group x experiment
        f"WITH g, {gk} AS group_key, e.id AS eid,"
        " collect(r) AS exp_edges\n"
        # Aggregate: per gene x group
        "WITH g, group_key,\n"
        "     count(eid) AS experiments_tested,\n"
        "     count(CASE WHEN ANY(x IN exp_edges"
        " WHERE x.expression_status = 'significant_up')"
        " THEN 1 END) AS experiments_up,\n"
        "     count(CASE WHEN ANY(x IN exp_edges"
        " WHERE x.expression_status = 'significant_down')"
        " THEN 1 END) AS experiments_down,\n"
        "     reduce(acc = [], edges IN collect(exp_edges)"
        " | acc + edges) AS all_edges\n"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       group_key,\n"
        "       experiments_tested,\n"
        "       experiments_up,\n"
        "       experiments_down,\n"
        "       size(all_edges) AS timepoints_tested,\n"
        "       size([x IN all_edges"
        " WHERE x.expression_status = 'significant_up'])"
        " AS timepoints_up,\n"
        "       size([x IN all_edges"
        " WHERE x.expression_status = 'significant_down'])"
        " AS timepoints_down,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_up'"
        " | x.rank_up] AS rank_ups,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_down'"
        " | x.rank_down] AS rank_downs,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_up'"
        " | x.log2_fold_change] AS log2fcs_up,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_down'"
        " | x.log2_fold_change] AS log2fcs_down\n"
        "ORDER BY locus_tag ASC, group_key ASC"
    )
    return cypher, params
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneResponseProfile -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(kg): add gene_response_profile aggregation query builder"
```

---

### Task 5: gene_response_profile API function

**Files:**
- Modify: `multiomics_explorer/api/functions.py`
- Modify: `multiomics_explorer/api/__init__.py`
- Modify: `multiomics_explorer/__init__.py`
- Test: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_api_functions.py`, add:

```python
class TestGeneResponseProfile:
    """Tests for gene_response_profile API function."""

    def _make_envelope_result(
        self,
        found=None,
        organism="Prochlorococcus marinus subsp. pastoris str. CCMP1986",
        has_expression=None,
        has_significant=None,
        group_totals=None,
    ):
        """Helper to build mock Q1 (envelope) result."""
        return [{
            "found_genes": found or ["PMM0370"],
            "organism_name": organism,
            "has_expression": has_expression or ["PMM0370"],
            "has_significant": has_significant or ["PMM0370"],
            "group_totals": group_totals or [
                {"group_key": "nitrogen_stress", "experiments": 4, "timepoints": 14},
                {"group_key": "coculture", "experiments": 2, "timepoints": 6},
            ],
        }]

    def _make_agg_rows(self):
        """Helper to build mock Q2 (aggregation) rows."""
        return [
            {
                "locus_tag": "PMM0370",
                "gene_name": "cynA",
                "product": "cyanate transporter",
                "gene_category": "Inorganic ion transport",
                "group_key": "nitrogen_stress",
                "experiments_tested": 3,
                "timepoints_tested": 8,
                "timepoints_up": 8,
                "timepoints_down": 0,
                "rank_ups": [3, 5, 8, 10, 12, 7, 6, 9],
                "rank_downs": [],
                "log2fcs_up": [5.7, 4.2, 3.1, 2.8, 2.5, 3.5, 3.8, 2.9],
                "log2fcs_down": [],
                "experiments_up": 3,
                "experiments_down": 0,
            },
            {
                "locus_tag": "PMM0370",
                "gene_name": "cynA",
                "product": "cyanate transporter",
                "gene_category": "Inorganic ion transport",
                "group_key": "coculture",
                "experiments_tested": 2,
                "timepoints_tested": 5,
                "timepoints_up": 0,
                "timepoints_down": 5,
                "rank_ups": [],
                "rank_downs": [12, 15, 14, 16, 18],
                "log2fcs_up": [],
                "log2fcs_down": [-13.0, -10.2, -8.5, -7.1, -6.0],
                "experiments_up": 0,
                "experiments_down": 2,
            },
        ]

    def test_returns_dict_with_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0370"], conn=mock_conn,
        )
        assert isinstance(result, dict)
        assert "results" in result
        assert "genes_queried" in result
        assert "genes_with_response" in result
        assert "returned" in result
        assert "truncated" in result
        assert "not_found" in result
        assert "no_expression" in result
        assert "organism_name" in result
        assert "offset" in result

    def test_not_found(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(found=["PMM0370"]),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0370", "FAKE999"], conn=mock_conn,
        )
        assert "FAKE999" in result["not_found"]

    def test_no_expression(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(
                found=["PMM0370", "PMM1234"],
                has_expression=["PMM0370"],
            ),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0370", "PMM1234"], conn=mock_conn,
        )
        assert "PMM1234" in result["no_expression"]

    def test_response_summary_structure(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0370"], conn=mock_conn,
        )
        gene = result["results"][0]
        assert "response_summary" in gene
        ns = gene["response_summary"]["nitrogen_stress"]
        assert ns["experiments_total"] == 4
        assert ns["experiments_tested"] == 3
        assert ns["experiments_up"] == 3
        assert ns["experiments_down"] == 0
        assert ns["timepoints_total"] == 14
        assert ns["timepoints_tested"] == 8
        assert ns["timepoints_up"] == 8
        assert ns["timepoints_down"] == 0

    def test_directional_fields_present_when_up(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0370"], conn=mock_conn,
        )
        ns = result["results"][0]["response_summary"]["nitrogen_stress"]
        assert "up_best_rank" in ns
        assert "up_median_rank" in ns
        assert "up_max_log2fc" in ns
        assert ns["up_best_rank"] == 3
        assert ns["up_max_log2fc"] == 5.7

    def test_directional_fields_absent_when_no_up(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0370"], conn=mock_conn,
        )
        cc = result["results"][0]["response_summary"]["coculture"]
        assert "up_best_rank" not in cc
        assert "up_median_rank" not in cc
        assert "up_max_log2fc" not in cc
        assert "down_best_rank" in cc
        assert cc["down_best_rank"] == 12

    def test_triage_lists(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0370"], conn=mock_conn,
        )
        gene = result["results"][0]
        assert "nitrogen_stress" in gene["groups_responded"]
        assert "coculture" in gene["groups_responded"]
        assert gene["groups_not_responded"] == []
        assert gene["groups_not_known"] == []

    def test_groups_not_known(self, mock_conn):
        """Gene has edges for nitrogen_stress but not coculture."""
        agg_rows = [self._make_agg_rows()[0]]  # only nitrogen_stress
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(),
            agg_rows,
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0370"], conn=mock_conn,
        )
        gene = result["results"][0]
        assert "coculture" in gene["groups_not_known"]

    def test_pagination(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._make_envelope_result(
                found=["PMM0001", "PMM0002", "PMM0003"],
                has_significant=["PMM0001", "PMM0002", "PMM0003"],
                has_expression=["PMM0001", "PMM0002", "PMM0003"],
            ),
            # Q2 only returns genes for limit=2
            [
                {**self._make_agg_rows()[0], "locus_tag": "PMM0001"},
                {**self._make_agg_rows()[0], "locus_tag": "PMM0002"},
            ],
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0001", "PMM0002", "PMM0003"],
            limit=2, conn=mock_conn,
        )
        assert result["returned"] == 2
        assert result["truncated"] is True
        assert result["genes_queried"] == 3

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError, match="locus_tags"):
            api.gene_response_profile(locus_tags=[], conn=mock_conn)

    def test_invalid_group_by_raises(self, mock_conn):
        with pytest.raises(ValueError, match="group_by"):
            api.gene_response_profile(
                locus_tags=["PMM0370"], group_by="bad", conn=mock_conn,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_api_functions.py::TestGeneResponseProfile -v`
Expected: FAIL — `gene_response_profile` not found in api module

- [ ] **Step 3: Implement the API function**

In `multiomics_explorer/api/functions.py`, add the import for the new builders at the top:

```python
from multiomics_explorer.kg.queries_lib import (
    # ... existing imports ...
    build_gene_response_profile_envelope,
    build_gene_response_profile,
)
```

Then add the function:

```python
def gene_response_profile(
    locus_tags: list[str],
    organism: str | None = None,
    treatment_types: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Cross-experiment gene-level response profile.

    Returns one result per gene summarizing its expression response
    across all experiments, grouped by treatment_type or experiment.

    Raises:
        ValueError: if locus_tags is empty, group_by is invalid,
            or organism validation fails.

    Returns:
        dict with keys: organism_name, genes_queried, genes_with_response,
        not_found, no_expression, returned, offset, truncated, results.
        Each result has: locus_tag, gene_name, product, gene_category,
        groups_responded, groups_not_responded, groups_not_known,
        response_summary.
    """
    if not locus_tags:
        raise ValueError(
            "locus_tags must not be empty. "
            "Use resolve_gene or gene_overview to find locus_tags."
        )
    if group_by not in ("treatment_type", "experiment"):
        raise ValueError(
            f"group_by must be 'treatment_type' or 'experiment', got '{group_by}'"
        )

    conn = _default_conn(conn)

    # Q1: Envelope — gene existence, expression flags, group totals
    env_cypher, env_params = build_gene_response_profile_envelope(
        locus_tags=locus_tags,
        organism=organism,
        treatment_types=treatment_types,
        experiment_ids=experiment_ids,
        group_by=group_by,
    )
    env_row = conn.execute_query(env_cypher, **env_params)[0]

    found_genes = env_row["found_genes"]
    has_expression = set(env_row["has_expression"])
    has_significant = set(env_row["has_significant"])
    organism_name = env_row["organism_name"]
    group_totals = {
        gt["group_key"]: {
            "experiments": gt["experiments"],
            "timepoints": gt["timepoints"],
        }
        for gt in env_row["group_totals"]
        if gt["group_key"] is not None
    }

    not_found = [lt for lt in locus_tags if lt not in found_genes]
    no_expression = [lt for lt in found_genes if lt not in has_expression]
    genes_with_response = len(has_significant)

    # Q2: Aggregation — per gene x group detail (paginated)
    agg_cypher, agg_params = build_gene_response_profile(
        locus_tags=[lt for lt in found_genes if lt in has_expression],
        organism=organism,
        treatment_types=treatment_types,
        experiment_ids=experiment_ids,
        group_by=group_by,
        limit=limit,
        offset=offset,
    )
    agg_rows = conn.execute_query(agg_cypher, **agg_params)

    # Pivot flat rows into per-gene nested structure
    genes_dict: dict[str, dict] = {}
    for row in agg_rows:
        lt = row["locus_tag"]
        if lt not in genes_dict:
            genes_dict[lt] = {
                "locus_tag": lt,
                "gene_name": row["gene_name"],
                "product": row["product"],
                "gene_category": row["gene_category"],
                "response_summary": {},
            }
        group_key = row["group_key"]
        totals = group_totals.get(group_key, {"experiments": 0, "timepoints": 0})

        entry: dict = {
            "experiments_total": totals["experiments"],
            "experiments_tested": row["experiments_tested"],
            "experiments_up": row["experiments_up"],
            "experiments_down": row["experiments_down"],
            "timepoints_total": totals["timepoints"],
            "timepoints_tested": row["timepoints_tested"],
            "timepoints_up": row["timepoints_up"],
            "timepoints_down": row["timepoints_down"],
        }

        # Directional rank/log2fc — only when experiments in that direction
        rank_ups = [r for r in row["rank_ups"] if r is not None]
        if rank_ups:
            entry["up_best_rank"] = min(rank_ups)
            entry["up_median_rank"] = statistics.median(rank_ups)
            entry["up_max_log2fc"] = max(row["log2fcs_up"])

        rank_downs = [r for r in row["rank_downs"] if r is not None]
        if rank_downs:
            entry["down_best_rank"] = min(rank_downs)
            entry["down_median_rank"] = statistics.median(rank_downs)
            entry["down_max_log2fc"] = min(row["log2fcs_down"])

        genes_dict[lt]["response_summary"][group_key] = entry

    # Build triage lists per gene
    results = []
    for gene in genes_dict.values():
        rs = gene["response_summary"]
        gene["groups_responded"] = [
            gk for gk, v in rs.items()
            if v["experiments_up"] > 0 or v["experiments_down"] > 0
        ]
        gene["groups_not_responded"] = [
            gk for gk, v in rs.items()
            if v["experiments_up"] == 0 and v["experiments_down"] == 0
        ]
        gene["groups_not_known"] = [
            gk for gk in group_totals
            if gk not in rs
        ]
        results.append(gene)

    # Determine truncation
    genes_with_expression = len(has_expression) - len(
        [lt for lt in found_genes if lt not in has_expression]
    )
    truncated = (
        len(results) + offset < genes_with_expression
        if limit is not None
        else False
    )

    return {
        "organism_name": organism_name,
        "genes_queried": len(locus_tags),
        "genes_with_response": genes_with_response,
        "not_found": not_found,
        "no_expression": no_expression,
        "returned": len(results),
        "offset": offset,
        "truncated": truncated,
        "results": results,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_api_functions.py::TestGeneResponseProfile -v`
Expected: PASS

- [ ] **Step 5: Add to exports**

In `multiomics_explorer/api/__init__.py`, add `gene_response_profile` to both the import and `__all__`:

```python
from multiomics_explorer.api.functions import (
    # ... existing ...
    gene_response_profile,
)

__all__ = [
    # ... existing ...
    "gene_response_profile",
]
```

Do the same in `multiomics_explorer/__init__.py`.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py multiomics_explorer/__init__.py tests/unit/test_api_functions.py
git commit -m "feat(api): add gene_response_profile function"
```

---

### Task 6: gene_response_profile MCP wrapper + Pydantic models

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Test: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_tool_wrappers.py`, update `EXPECTED_TOOLS`:

```python
EXPECTED_TOOLS = [
    "kg_schema", "list_filter_values", "list_organisms", "resolve_gene",
    "genes_by_function", "gene_overview", "gene_details",
    "gene_homologs", "run_cypher",
    "search_ontology", "search_homolog_groups", "genes_by_homolog_group",
    "genes_by_ontology", "gene_ontology_terms",
    "list_publications",
    "list_experiments",
    "differential_expression_by_gene",
    "differential_expression_by_ortholog",
    "gene_response_profile",
]
```

Then add the test class:

```python
class TestGeneResponseProfileWrapper:
    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.side_effect = [
            # Q1 envelope
            [{
                "found_genes": ["PMM0370"],
                "organism_name": "Prochlorococcus MED4",
                "has_expression": ["PMM0370"],
                "has_significant": ["PMM0370"],
                "group_totals": [
                    {"group_key": "nitrogen_stress",
                     "experiments": 4, "timepoints": 14},
                ],
            }],
            # Q2 aggregation
            [{
                "locus_tag": "PMM0370",
                "gene_name": "cynA",
                "product": "cyanate transporter",
                "gene_category": "Inorganic ion transport",
                "group_key": "nitrogen_stress",
                "experiments_tested": 3,
                "timepoints_tested": 8,
                "timepoints_up": 8,
                "timepoints_down": 0,
                "rank_ups": [3, 5, 8],
                "rank_downs": [],
                "log2fcs_up": [5.7, 4.2, 3.1],
                "log2fcs_down": [],
                "experiments_up": 3,
                "experiments_down": 0,
            }],
        ]
        result = await tool_fns["gene_response_profile"](
            mock_ctx, locus_tags=["PMM0370"],
        )
        assert hasattr(result, "results")
        assert hasattr(result, "genes_queried")
        assert hasattr(result, "returned")
        assert hasattr(result, "truncated")
        assert hasattr(result, "organism_name")

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.side_effect = [
            [{
                "found_genes": [],
                "organism_name": None,
                "has_expression": [],
                "has_significant": [],
                "group_totals": [],
            }],
            [],
        ]
        result = await tool_fns["gene_response_profile"](
            mock_ctx, locus_tags=["FAKE999"],
        )
        assert result.results == []
        assert result.returned == 0

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.side_effect = ValueError("bad")
        with pytest.raises(ToolError):
            await tool_fns["gene_response_profile"](
                mock_ctx, locus_tags=["PMM0370"],
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tool_wrappers.py::TestGeneResponseProfileWrapper -v`
Expected: FAIL — tool not registered

- [ ] **Step 3: Implement Pydantic models + wrapper**

In `multiomics_explorer/mcp_server/tools.py`, inside `register_tools()`, add the Pydantic models and tool wrapper:

```python
    # --- gene_response_profile ---

    class GeneResponseGroupSummary(BaseModel):
        experiments_total: int = Field(
            description="Total experiments for this group in the organism"
            " (e.g. 4)",
        )
        experiments_tested: int = Field(
            description="Experiments where this gene has expression edges"
            " (e.g. 3)",
        )
        experiments_up: int = Field(
            description="Experiments with significant_up in at least"
            " one timepoint (e.g. 3)",
        )
        experiments_down: int = Field(
            description="Experiments with significant_down in at least"
            " one timepoint (e.g. 0)",
        )
        timepoints_total: int = Field(
            description="Total timepoints across experiments for this"
            " group (e.g. 14)",
        )
        timepoints_tested: int = Field(
            description="Timepoints where gene has an expression edge"
            " (e.g. 8)",
        )
        timepoints_up: int = Field(
            description="Timepoints where gene is significant_up (e.g. 8)",
        )
        timepoints_down: int = Field(
            description="Timepoints where gene is significant_down (e.g. 0)",
        )
        up_best_rank: int | None = Field(
            default=None,
            description="Best (lowest) rank_up across significant_up"
            " timepoints. 1 = strongest. Present only when"
            " experiments_up > 0.",
        )
        up_median_rank: float | None = Field(
            default=None,
            description="Median rank_up across significant_up timepoints."
            " Present only when experiments_up > 0.",
        )
        up_max_log2fc: float | None = Field(
            default=None,
            description="Largest positive log2FC across significant_up"
            " timepoints. Present only when experiments_up > 0.",
        )
        down_best_rank: int | None = Field(
            default=None,
            description="Best (lowest) rank_down across significant_down"
            " timepoints. 1 = strongest. Present only when"
            " experiments_down > 0.",
        )
        down_median_rank: float | None = Field(
            default=None,
            description="Median rank_down across significant_down"
            " timepoints. Present only when experiments_down > 0.",
        )
        down_max_log2fc: float | None = Field(
            default=None,
            description="Most negative log2FC across significant_down"
            " timepoints. Present only when experiments_down > 0.",
        )

    class GeneResponseProfileResult(BaseModel):
        locus_tag: str = Field(
            description="Gene locus tag (e.g. 'PMM0370')",
        )
        gene_name: str | None = Field(
            description="Gene name (e.g. 'cynA'). Null if unannotated.",
        )
        product: str | None = Field(
            description="Gene product description"
            " (e.g. 'cyanate transporter')",
        )
        gene_category: str | None = Field(
            description="Functional category"
            " (e.g. 'Inorganic ion transport')",
        )
        groups_responded: list[str] = Field(
            description="Groups where gene is significant in at least"
            " one timepoint",
        )
        groups_not_responded: list[str] = Field(
            description="Groups where expression edges exist but none"
            " significant",
        )
        groups_not_known: list[str] = Field(
            description="Groups with no expression edge for this gene",
        )
        response_summary: dict[str, GeneResponseGroupSummary] = Field(
            description="Per-group detail. Keys are treatment types"
            " or experiment IDs depending on group_by.",
        )

    class GeneResponseProfileResponse(BaseModel):
        organism_name: str | None = Field(
            description="Resolved organism name",
        )
        genes_queried: int = Field(
            description="Count of input locus_tags (e.g. 17)",
        )
        genes_with_response: int = Field(
            description="Genes with at least one significant expression"
            " edge (e.g. 15)",
        )
        not_found: list[str] = Field(
            default_factory=list,
            description="Input locus_tags not found in KG",
        )
        no_expression: list[str] = Field(
            default_factory=list,
            description="Gene exists but has zero expression edges",
        )
        returned: int = Field(
            description="Genes in results after pagination (e.g. 15)",
        )
        offset: int = Field(
            description="Offset into paginated gene list (e.g. 0)",
        )
        truncated: bool = Field(
            description="True if more genes available beyond"
            " returned + offset",
        )
        results: list[GeneResponseProfileResult] = Field(
            default_factory=list,
        )

    @mcp.tool(
        tags={"expression", "gene"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def gene_response_profile(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags. E.g. ['PMM0370', 'PMM0920']."
            " Get these from resolve_gene / gene_overview.",
        )],
        organism: Annotated[str | None, Field(
            description="Organism name for validation (optional)."
            " Inferred from genes. Fuzzy word-based matching.",
        )] = None,
        treatment_types: Annotated[list[str] | None, Field(
            description="Filter to specific treatment types.",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Restrict to specific experiments."
            " Get these from list_experiments.",
        )] = None,
        group_by: Annotated[
            Literal["treatment_type", "experiment"], Field(
                description="Group response summary by treatment_type"
                " (aggregates across experiments) or experiment"
                " (one entry per experiment).",
            ),
        ] = "treatment_type",
        limit: Annotated[int, Field(
            description="Max genes returned.", ge=1,
        )] = 50,
        offset: Annotated[int, Field(
            description="Skip N genes for pagination.", ge=0,
        )] = 0,
    ) -> GeneResponseProfileResponse:
        """Cross-experiment gene response profile.

        Summarizes how each gene responds across all experiments. One result
        per gene with response_summary showing per-treatment (or per-experiment)
        statistics: how many experiments/timepoints the gene was tested in,
        how many it responded in (up/down), and rank/log2fc stats for
        significant responses.

        Results sorted by response breadth: genes responding to most groups
        first, then by experiment count, then by timepoint count.

        Use differential_expression_by_gene to drill into temporal patterns
        within a specific experiment.
        """
        await ctx.info(
            f"gene_response_profile locus_tags={locus_tags}"
            f" group_by={group_by} limit={limit}"
        )
        try:
            conn = _conn(ctx)
            data = api.gene_response_profile(
                locus_tags=locus_tags,
                organism=organism,
                treatment_types=treatment_types,
                experiment_ids=experiment_ids,
                group_by=group_by,
                limit=limit,
                offset=offset,
                conn=conn,
            )
            data["results"] = [
                GeneResponseProfileResult(
                    **{
                        **{k: v for k, v in r.items()
                           if k != "response_summary"},
                        "response_summary": {
                            gk: GeneResponseGroupSummary(**gv)
                            for gk, gv in r["response_summary"].items()
                        },
                    }
                )
                for r in data["results"]
            ]
            response = GeneResponseProfileResponse(**data)
            await ctx.info(
                f"Returning {response.returned} of"
                f" {response.genes_queried} genes"
                f" ({response.genes_with_response} with response)"
            )
            return response
        except ValueError as e:
            await ctx.warning(f"gene_response_profile error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_response_profile unexpected error: {e}")
            raise ToolError(f"Error in gene_response_profile: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tool_wrappers.py::TestGeneResponseProfileWrapper -v`
Expected: PASS

Also run: `pytest tests/unit/test_tool_wrappers.py::test_all_tools_registered -v`
Expected: PASS (gene_response_profile now in EXPECTED_TOOLS)

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat(mcp): add gene_response_profile tool with Pydantic models"
```

---

### Task 7: CLAUDE.md + about YAML + build

**Files:**
- Modify: `CLAUDE.md`
- Create: `multiomics_explorer/inputs/tools/gene_response_profile.yaml`

- [ ] **Step 1: Add tool to CLAUDE.md table**

In `CLAUDE.md`, add to the tools table after `differential_expression_by_ortholog`:

```markdown
| `gene_response_profile` | Cross-experiment gene-level summary: how each gene responds across treatments/experiments. One result per gene with response breadth, rank stats, log2FC stats. Sorted by response breadth. |
```

- [ ] **Step 2: Create about YAML**

Create `multiomics_explorer/inputs/tools/gene_response_profile.yaml`:

```yaml
# Human-authored content for gene_response_profile about page.
# Auto-generated sections (params, response format, expected-keys)
# come from Pydantic models via scripts/build_about_content.py.

examples:
  - title: Gene response overview
    call: gene_response_profile(locus_tags=["PMM0370", "PMM0920"])
    response: |
      {"organism_name": "Prochlorococcus marinus subsp. pastoris str. CCMP1986", "genes_queried": 2, "genes_with_response": 2, "not_found": [], "no_expression": [], "returned": 2, "offset": 0, "truncated": false, "results": [{"locus_tag": "PMM0370", "gene_name": "cynA", "product": "cyanate transporter", "gene_category": "Inorganic ion transport", "groups_responded": ["nitrogen_stress", "coculture"], "groups_not_responded": ["light_stress"], "groups_not_known": [], "response_summary": {"nitrogen_stress": {"experiments_total": 4, "experiments_tested": 3, "experiments_up": 3, "experiments_down": 0, "timepoints_total": 14, "timepoints_tested": 8, "timepoints_up": 8, "timepoints_down": 0, "up_best_rank": 3, "up_median_rank": 8.0, "up_max_log2fc": 5.7}}}]}

  - title: Filter by treatment type
    call: gene_response_profile(locus_tags=["PMM0370"], treatment_types=["nitrogen_stress", "coculture"])

  - title: Per-experiment breakdown
    call: gene_response_profile(locus_tags=["PMM0370"], group_by="experiment")

  - title: Chaining — find responsive genes then profile them
    steps: |
      Step 1: genes_by_function(search_text="nitrogen transport", organism="MED4")
              → collect locus_tags from results

      Step 2: gene_response_profile(locus_tags=["PMM0370", ...])
              → see which treatments each gene responds to

      Step 3: differential_expression_by_gene(locus_tags=["PMM0370"], experiment_ids=["..."])
              → drill into time course for a specific experiment

chaining:
  - "genes_by_function → gene_response_profile"
  - "genes_by_ontology → gene_response_profile"
  - "gene_overview → gene_response_profile (check expression_edge_count first)"
  - "gene_response_profile → differential_expression_by_gene (drill into specific experiment)"

mistakes:
  - wrong: "Assuming groups_not_known means 'gene does not respond to this treatment'"
    right: "groups_not_known means no expression data exists — the gene was not profiled or not reported for that treatment. Check experiments_total in the response_summary for coverage."
  - wrong: "Comparing up_max_log2fc across different organisms or platforms"
    right: "log2FC magnitudes are not directly comparable across platforms (microarray vs RNA-seq). Ranks are comparable."
  - wrong: "Using this tool to see time course dynamics"
    right: "This tool aggregates across timepoints. Use differential_expression_by_gene with a specific experiment to see temporal patterns."
  - "Results are sorted by response breadth — genes responding to more treatments appear first"
  - "Single organism enforced — call once per organism"
```

- [ ] **Step 3: Build about content**

Run: `uv run python scripts/build_about_content.py gene_response_profile`

- [ ] **Step 4: Run about content tests**

Run: `pytest tests/unit/test_about_content.py -v -k gene_response_profile`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md multiomics_explorer/inputs/tools/gene_response_profile.yaml multiomics_explorer/skills/
git commit -m "docs: add gene_response_profile to CLAUDE.md and about content"
```

---

### Task 8: Integration test registrations

**Files:**
- Modify: `tests/integration/test_cyver_queries.py`
- Modify: `tests/integration/test_api_contract.py`
- Modify: `tests/regression/test_regression.py`

- [ ] **Step 1: Add builders to CyVer `_BUILDERS` list**

In `tests/integration/test_cyver_queries.py`, add imports:

```python
from multiomics_explorer.kg.queries_lib import (
    # ... existing ...
    build_gene_response_profile_envelope,
    build_gene_response_profile,
)
```

Add entries to `_BUILDERS`:

```python
    # --- gene_response_profile ---
    ("gene_response_profile_envelope", build_gene_response_profile_envelope,
     {"locus_tags": _LOCUS}),
    ("gene_response_profile", build_gene_response_profile,
     {"locus_tags": _LOCUS}),
    ("gene_response_profile_by_experiment", build_gene_response_profile,
     {"locus_tags": _LOCUS, "group_by": "experiment"}),
```

- [ ] **Step 2: Add API contract test**

In `tests/integration/test_api_contract.py`, add:

```python
@pytest.mark.kg
class TestGeneResponseProfileContract:
    def test_returns_dict_envelope(self, conn):
        result = api.gene_response_profile(
            locus_tags=[KNOWN_GENE], conn=conn,
        )
        assert isinstance(result, dict)
        expected_keys = {
            "organism_name", "genes_queried", "genes_with_response",
            "not_found", "no_expression",
            "returned", "offset", "truncated", "results",
        }
        assert set(result.keys()) == expected_keys

    def test_result_structure(self, conn):
        result = api.gene_response_profile(
            locus_tags=[KNOWN_GENE], conn=conn,
        )
        assert result["returned"] >= 1
        gene = result["results"][0]
        for key in ("locus_tag", "gene_name", "product", "gene_category",
                     "groups_responded", "groups_not_responded",
                     "groups_not_known", "response_summary"):
            assert key in gene

    def test_response_summary_fields(self, conn):
        result = api.gene_response_profile(
            locus_tags=[KNOWN_GENE], conn=conn,
        )
        gene = result["results"][0]
        if gene["response_summary"]:
            entry = next(iter(gene["response_summary"].values()))
            for key in ("experiments_total", "experiments_tested",
                         "experiments_up", "experiments_down",
                         "timepoints_total", "timepoints_tested",
                         "timepoints_up", "timepoints_down"):
                assert key in entry
```

- [ ] **Step 3: Add to regression TOOL_BUILDERS**

In `tests/regression/test_regression.py`, add import and entry:

```python
from multiomics_explorer.kg.queries_lib import (
    # ... existing ...
    build_gene_response_profile,
)

TOOL_BUILDERS = {
    # ... existing ...
    "gene_response_profile": build_gene_response_profile,
}
```

Add regression test cases to `tests/evals/cases.yaml`:

```yaml
- id: gene_response_profile_basic
  tool: gene_response_profile
  desc: Basic gene response profile for known gene
  params:
    locus_tags: ["PMM0370"]
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, group_key]
    row0:
      locus_tag: PMM0370
```

- [ ] **Step 4: Run CyVer tests**

Run: `pytest tests/integration/test_cyver_queries.py -v -k gene_response_profile -m kg`
Expected: PASS

- [ ] **Step 5: Run API contract tests**

Run: `pytest tests/integration/test_api_contract.py::TestGeneResponseProfileContract -v -m kg`
Expected: PASS

- [ ] **Step 6: Generate regression baselines**

Run: `pytest tests/regression/ --force-regen -m kg -k gene_response_profile`
Verify: `git diff tests/regression/` — inspect generated baseline

- [ ] **Step 7: Run full unit + integration test suite**

Run: `pytest tests/unit/ -v && pytest -m kg -v`
Expected: all PASS

- [ ] **Step 8: Verify MCP server starts**

Run: `uv run python -c "from multiomics_explorer.mcp_server.server import mcp; print('OK')"`
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add tests/integration/ tests/regression/ tests/evals/
git commit -m "test: add gene_response_profile integration and regression tests"
```
