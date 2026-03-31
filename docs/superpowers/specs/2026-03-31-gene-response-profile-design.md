# gene_response_profile MCP tool

## Problem

The existing `differential_expression_by_gene` tool returns one row per gene × experiment × timepoint. Answering "which stresses does this gene respond to?" requires querying all experiments, collecting all rows, and manually aggregating. For batch gene lists across many experiments, this exceeds LLM context and forces ad hoc workarounds.

## Scope

New MCP tool `gene_response_profile` across all 4 layers of multiomics_explorer, plus a small update to `differential_expression_by_gene` to expose directional rank fields.

| Layer | File | What it adds |
|---|---|---|
| Schema baseline | `config/schema_baseline.yaml` | Add `rank_up`, `rank_down` to `Changes_expression_of` properties |
| Query builder | `kg/queries_lib.py` | `build_gene_response_profile_envelope`, `build_gene_response_profile` |
| API function | `api/functions.py` | `gene_response_profile()` |
| MCP wrapper | `mcp_server/tools.py` | `gene_response_profile` tool + Pydantic response models |
| About YAML | `inputs/tools/gene_response_profile.yaml` | Examples, chaining, mistakes |
| About MD | `skills/.../references/tools/gene_response_profile.md` | Auto-generated via `build_about_content.py` |
| Tests | `tests/unit/`, `tests/integration/` | Unit + KG integration |
| CLAUDE.md | `CLAUDE.md` | Add tool to table |

Also updates `differential_expression_by_gene`:
- Query builder: add `rank_up`, `rank_down` to RETURN clause
- API: pass through new fields
- MCP: add fields to `ExpressionRow` Pydantic model
- About YAML/MD: document new fields

### Prerequisites

- KG already has `rank_up`/`rank_down` on `Changes_expression_of` edges (done).

### Not in scope

- Analysis utilities (`response_matrix`, `gene_set_compare`) — separate spec
- Changes to biocypher_kg
- Time course visualization

## Parameters

| Name | Type | Default | Required | Description |
|---|---|---|---|---|
| `locus_tags` | list[string] | — | yes | Gene locus tags |
| `organism` | string \| None | None | no | Validation only — organism is inferred from genes. If provided, validates they match. Fuzzy word-based matching. |
| `treatment_types` | list[string] \| None | None | no | Filter to specific treatment types |
| `experiment_ids` | list[string] \| None | None | no | Restrict to specific experiments |
| `group_by` | Literal["treatment_type", "experiment"] | "treatment_type" | no | How to group the response summary. `"treatment_type"`: aggregates across experiments per treatment. `"experiment"`: one entry per experiment, no cross-experiment aggregation. |
| `limit` | int | 50 | no | Max genes returned (pagination on gene axis) |
| `offset` | int | 0 | no | Skip N genes for pagination |

### Differences from existing expression tools

- No `direction` or `significant_only` — this tool summarizes all expression data; filtering is in the response fields
- No `verbose` — all fields are needed for the summary to be interpretable
- No `summary` mode — the tool *is* a summary tool
- `limit`/`offset` paginate on the gene axis, not on gene × experiment × timepoint rows
- Single organism enforced (same as `differential_expression_by_gene`). `organism` param is for validation, not filtering.

## Response format

### Envelope

```json
{
  "organism_name": "Prochlorococcus marinus subsp. pastoris str. CCMP1986",
  "genes_queried": 17,
  "genes_with_response": 15,
  "not_found": [],
  "no_expression": ["PMM1234"],
  "returned": 15,
  "offset": 0,
  "truncated": false,
  "results": []
}
```

| Field | Type | Description |
|---|---|---|
| `organism_name` | string | Resolved organism name |
| `genes_queried` | int | Count of input locus_tags |
| `genes_with_response` | int | Genes with ≥1 significant expression edge |
| `not_found` | list[string] | Input locus_tags not in KG |
| `no_expression` | list[string] | Gene exists but has zero expression edges |
| `returned` | int | Genes in results (after pagination) |
| `offset` | int | Offset into paginated gene list |
| `truncated` | bool | True if more genes available beyond returned + offset |

### Per-gene result

```json
{
  "locus_tag": "PMM0370",
  "gene_name": "cynA",
  "product": "cyanate transporter",
  "gene_category": "Inorganic ion transport",
  "groups_responded": ["nitrogen_stress", "coculture"],
  "groups_not_responded": ["light_stress", "iron_stress"],
  "groups_not_known": ["salt_stress"],
  "response_summary": {
    "nitrogen_stress": {
      "experiments_total": 4,
      "experiments_tested": 3,
      "experiments_up": 3,
      "experiments_down": 0,
      "timepoints_total": 14,
      "timepoints_tested": 8,
      "timepoints_up": 8,
      "timepoints_down": 0,
      "up_best_rank": 3,
      "up_median_rank": 8.0,
      "up_max_log2fc": 5.7
    },
    "coculture": {
      "experiments_total": 2,
      "experiments_tested": 2,
      "experiments_up": 0,
      "experiments_down": 2,
      "timepoints_total": 6,
      "timepoints_tested": 5,
      "timepoints_up": 0,
      "timepoints_down": 5,
      "down_best_rank": 12,
      "down_median_rank": 15.0,
      "down_max_log2fc": -13.0
    }
  }
}
```

### Per-gene fields

| Field | Type | Description |
|---|---|---|
| `locus_tag` | string | Gene identifier |
| `gene_name` | string \| None | Gene name (null if unannotated) |
| `product` | string \| None | Gene product description |
| `gene_category` | string \| None | Functional category |
| `groups_responded` | list[string] | Groups where gene is significant in ≥1 timepoint |
| `groups_not_responded` | list[string] | Groups where expression edges exist but none significant |
| `groups_not_known` | list[string] | Groups where no expression edge exists for this gene |
| `response_summary` | dict[string, object] | Keys = group labels (treatment types or experiment IDs depending on `group_by`) |

### Per-group response_summary fields

Always present:

| Field | Type | Description |
|---|---|---|
| `experiments_total` | int | Total experiments for this group in the organism (denominator) |
| `experiments_tested` | int | Experiments where this gene has expression edges |
| `experiments_up` | int | Experiments where gene is significant_up in ≥1 timepoint |
| `experiments_down` | int | Experiments where gene is significant_down in ≥1 timepoint |
| `timepoints_total` | int | Total timepoints across all experiments for this group (denominator, from `e.time_point_count`) |
| `timepoints_tested` | int | Timepoints where this gene has an expression edge |
| `timepoints_up` | int | Timepoints where gene is significant_up |
| `timepoints_down` | int | Timepoints where gene is significant_down |

Present only when `experiments_up > 0`:

| Field | Type | Description |
|---|---|---|
| `up_best_rank` | int | Best (lowest) `rank_up` across all significant_up timepoints. 1 = strongest upregulated gene. |
| `up_median_rank` | float | Median `rank_up` across all significant_up timepoints |
| `up_max_log2fc` | float | Largest positive log2FC across all significant_up timepoints |

Present only when `experiments_down > 0`:

| Field | Type | Description |
|---|---|---|
| `down_best_rank` | int | Best (lowest) `rank_down` across all significant_down timepoints. 1 = strongest downregulated gene. |
| `down_median_rank` | float | Median `rank_down` across all significant_down timepoints |
| `down_max_log2fc` | float | Most negative log2FC across all significant_down timepoints |

### Triage list semantics

- **`groups_responded`** — significant (`significant_up` or `significant_down`) in ≥1 timepoint in ≥1 experiment for that group
- **`groups_not_responded`** — expression edges exist (gene was measured) but all are `not_significant`
- **`groups_not_known`** — no expression edge exists for this gene in any experiment for that group. The group exists for the organism but is absent from this gene's `response_summary`.

### Result ordering

Results are sorted by response breadth, then depth:

1. `len(groups_responded)` DESC — most groups first
2. Total experiments responded (sum of `experiments_up + experiments_down` across groups) DESC
3. Total timepoints responded (sum of `timepoints_up + timepoints_down` across groups) DESC
4. `locus_tag` ASC — deterministic tiebreaker

Sorting is done in Cypher via a two-pass query (see Query Strategy).

### What the tool does NOT return

- Averaged log2FC across experiments (different platforms/baselines)
- Combined p-values across experiments
- Single effect size across studies
- Gene classification labels (e.g. "N-specific") — analysis logic belongs in scripts
- Time course dynamics — use `differential_expression_by_gene` for temporal patterns per experiment

## Implementation conventions

### Layer 1: Query builders (`kg/queries_lib.py`)

Signature: `def build_gene_response_profile(*, locus_tags, organism_name, ...) -> tuple[str, dict]`

- All keyword-only args, returns `(cypher_string, params_dict)`
- `$param_name` placeholders — no f-string interpolation of user input
- `AS snake_case` aliases on all RETURN columns
- `organism_name` is the resolved (exact) name from `_validate_organism_inputs` — uses exact match (`e.organism_name = $organism_name`), not fuzzy
- Treatment type filter: `toLower(e.treatment_type) IN $treatment_types` with Python-side lowercasing
- NULL behavior in aggregation:
  - `collect(r.rank_up)` drops NULLs — safe for computing min/median over non-null ranks only
  - `percentileCont(CASE WHEN cond THEN val ELSE null END, 0.5)` — NULLs silently ignored, safe for conditional median
  - `sum(CASE WHEN cond THEN 1 ELSE 0 END)` — use explicit `ELSE 0`
- APOC available:
  - `apoc.coll.min()` for best_rank
  - Built-in `percentileCont()` for median_rank (not APOC — Neo4j native)
  - `reduce()` or list comprehensions for max log2fc

### Layer 2: API function (`api/functions.py`)

Signature:

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
```

- `conn` keyword-only, always last
- `limit=None` in API means all genes (MCP sets default)
- Returns dict with envelope fields + `results` list
- Raises `ValueError` for invalid inputs (empty locus_tags, invalid group_by, mixed organisms)
- Must be added to `api/__init__.py` and `multiomics_explorer/__init__.py` `__all__`

### Layer 3: MCP wrapper (`mcp_server/tools.py`)

- Thin — calls `api.gene_response_profile()`, validates via `Response(**data)`
- Default `limit=50` in MCP (higher than usual 5 because this is a summary tool — one row per gene, not per observation)
- `Annotated[..., Field(description=...)]` on all params
- `Literal["treatment_type", "experiment"]` for `group_by`
- Tags: `{"expression", "gene"}`, `annotations={"readOnlyHint": True}`

### Layer 4: About content

- Author `inputs/tools/gene_response_profile.yaml` with examples, chaining, mistakes
- Run `scripts/build_about_content.py gene_response_profile` to generate MD
- MD auto-placed at `skills/multiomics-kg-guide/references/tools/gene_response_profile.md`

## Query strategy

### Q1: Envelope (no pagination)

Computes global counts and group denominators for all input genes.

```
Inputs: $locus_tags, $organism (optional), $treatment_types (optional), $experiment_ids (optional), $group_by
Returns:
  - organism_name (resolved)
  - found genes, not_found, no_expression, genes_with_response
  - organism_groups: per-group {experiments, timepoints} using e.time_point_count (used internally to stamp denominators into per-gene results and derive groups_not_known)
```

### Q2: Aggregation (paginated in Cypher)

Two-pass Cypher query:

**Pass 1 — sort keys + paginate on gene axis:**

```cypher
MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)
WHERE g.locus_tag IN $locus_tags
WITH g,
     count(DISTINCT CASE WHEN r.expression_status IN ['significant_up','significant_down']
           THEN $group_key_expr END) AS groups_responded,
     count(DISTINCT CASE WHEN r.expression_status IN ['significant_up','significant_down']
           THEN e.id END) AS experiments_responded,
     sum(CASE WHEN r.expression_status IN ['significant_up','significant_down']
         THEN 1 ELSE 0 END) AS timepoints_responded
ORDER BY groups_responded DESC, experiments_responded DESC, timepoints_responded DESC, g.locus_tag ASC
SKIP $offset LIMIT $limit
```

Where `$group_key_expr` is `e.treatment_type` or `e.id` depending on `group_by`.

**Pass 2 — expand detail for paginated genes only:**

```cypher
WITH g
MATCH (e:Experiment)-[r:Changes_expression_of]->(g)
WITH g, $group_key_expr AS group_key, collect(r) AS edges, collect(DISTINCT e) AS experiments
RETURN g.locus_tag AS locus_tag,
       g.gene_name AS gene_name,
       g.product AS product,
       g.gene_category AS gene_category,
       group_key,
       size(experiments) AS experiments_tested,
       size([exp IN experiments WHERE ...]) AS experiments_up,
       size([exp IN experiments WHERE ...]) AS experiments_down,
       size(edges) AS timepoints_tested,
       size([e IN edges WHERE e.expression_status = 'significant_up']) AS timepoints_up,
       size([e IN edges WHERE e.expression_status = 'significant_down']) AS timepoints_down,
       -- rank and log2fc stats via reduce/list comprehensions
```

**Note:** The exact Cypher for rank/log2fc aggregation (min rank_up, median rank_up, max log2fc per direction) will be finalized during implementation. Options include `reduce()`, APOC `apoc.coll.min/avg`, or collect + post-process in API.

### API post-processing

1. Pivot Q2 flat rows (gene × group_key) into nested `response_summary` per gene
2. Stamp `experiments_total`/`timepoints_total` from Q1's organism_groups into each response_summary entry
3. Derive triage lists: `groups_responded` / `groups_not_responded` / `groups_not_known` from response_summary entries and organism_groups
4. Conditionally include/omit directional rank/log2fc fields based on `experiments_up > 0` / `experiments_down > 0`
5. Assemble envelope from Q1 + paginated results

## Update to differential_expression_by_gene

Small change to expose `rank_up` and `rank_down` from the already-present KG edge properties.

### Schema baseline

Add to `Changes_expression_of` properties in `config/schema_baseline.yaml`:

```yaml
rank_up: int
rank_down: int
```

### Query builder

Add to `build_differential_expression_by_gene` RETURN clause in `kg/queries_lib.py`:

```cypher
r.rank_up AS rank_up,
r.rank_down AS rank_down,
```

### API function

Pass through `rank_up` and `rank_down` — no post-processing needed.

### MCP wrapper

Add to `ExpressionRow` Pydantic model:

```python
rank_up: int | None = Field(None, description="Rank by |log2FC| among significant_up genes within experiment × timepoint. Null if not significant_up. 1 = strongest.")
rank_down: int | None = Field(None, description="Rank by |log2FC| among significant_down genes within experiment × timepoint. Null if not significant_down. 1 = strongest.")
```

### About YAML/MD

Update `inputs/tools/differential_expression_by_gene.yaml` verbose_fields list and any example responses that include rank fields. Rebuild about content.

## Testing strategy

### Query builder tests (`tests/unit/test_query_builders.py`)

Class: `TestBuildGeneResponseProfileEnvelope`, `TestBuildGeneResponseProfile`

- `test_basic` — required params, assert MATCH/RETURN/params
- `test_returns_expected_columns` — all RETURN aliases present
- `test_with_treatment_types` — filter appears in WHERE + params
- `test_with_experiment_ids` — filter appears in WHERE + params
- `test_group_by_experiment` — group key uses `e.id` not `e.treatment_type`
- `test_order_by` — ORDER BY with sort cascade present
- `test_skip_limit` — SKIP/LIMIT in Cypher

### API function tests (`tests/unit/test_api_functions.py`)

Class: `TestGeneResponseProfile`

- `test_returns_dict_with_results` — envelope fields + results list
- `test_empty_results` — no matching genes
- `test_not_found_field` — batch: missing locus_tags in `not_found`
- `test_no_expression_field` — gene exists but no edges → `no_expression`
- `test_triage_list_derivation` — gene with edges in some groups, not others → correct `groups_responded`/`groups_not_responded`/`groups_not_known`
- `test_directional_field_omission` — `up_*` absent when `experiments_up = 0`
- `test_pagination` — offset/limit applied on gene axis
- `test_sort_order` — breadth → depth → timepoints → locus_tag
- `test_group_by_experiment` — keys are experiment IDs, same structure
- `test_denominators_stamped` — `experiments_total`/`timepoints_total` present per group entry

Mock pattern: `mock_conn.execute_query.side_effect = [q1_result, q2_result]` (2-query function).

### MCP wrapper tests (`tests/unit/test_tool_wrappers.py`)

Class: `TestGeneResponseProfileWrapper`

- `test_returns_response_model` — Pydantic model with expected fields
- `test_empty_results`
- `test_default_limit` — MCP default limit = 50
- `test_value_error_raises_tool_error`
- `test_unexpected_error_raises_tool_error`
- Add `"gene_response_profile"` to `EXPECTED_TOOLS` list

### Registration checklists

| Registry | File | Action |
|---|---|---|
| `EXPECTED_TOOLS` | `tests/unit/test_tool_wrappers.py` | Add `"gene_response_profile"` |
| `TOOL_BUILDERS` | `tests/regression/test_regression.py` | Add `"gene_response_profile": build_gene_response_profile` |
| `_BUILDERS` | `tests/integration/test_cyver_queries.py` | Add envelope + aggregation builders with representative args |
| `Test*Contract` | `tests/integration/test_api_contract.py` | Add `TestGeneResponseProfileContract` |

### Integration tests (requires Neo4j)

**CyVer** (`tests/integration/test_cyver_queries.py`):
- Add both builders to `_BUILDERS` with representative args

**API contract** (`tests/integration/test_api_contract.py`):
- `TestGeneResponseProfileContract` — verify return dict shape and keys

**Correctness** (`tests/integration/test_tool_correctness_kg.py`):
- Known gene (e.g. cynA/PMM0370): verify response_summary against expected expression profile
- Gene with no expression data: appears in `no_expression`
- Mixed batch: some found, some not, some with expression, some without
- Filter by treatment_types: only matching groups in response_summary
- Filter by experiment_ids: scoped correctly
- `group_by="experiment"`: one entry per experiment, counts make sense

**Regression** (`tests/regression/`):
- Add cases to `cases.yaml`, generate baselines with `--force-regen`

**About content** (`tests/unit/test_about_content.py`):
- Auto-covered once YAML + MD are generated (expected-keys check, param name check)

### differential_expression_by_gene update

- Existing tests still pass with new `rank_up`/`rank_down` fields
- Update `ExpressionRow` expected fields in wrapper tests
- Update API contract expected keys
- `rank_up`/`rank_down` present for significant genes, null for non-significant
- Add to regression baselines: `pytest tests/regression/ --force-regen -m kg`
