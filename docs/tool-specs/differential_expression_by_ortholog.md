# Tool spec: differential_expression_by_ortholog

## Purpose

MCP tool returning expression results at group × experiment × timepoint
granularity (gene counts, not individual genes). Cross-organism by design.

Queries the intersection of two KG patterns:
- `(Gene)-[:Gene_in_ortholog_group]->(OrthologGroup)` — membership
- `(Experiment)-[:Changes_expression_of]->(Gene)` — expression

Direct Cypher (not a wrapper) — cross-organism aggregation in one
query is more efficient than per-organism iteration.

## Out of Scope

- **Group membership without expression** — use `genes_by_homolog_group`
- **Gene-centric expression (no group framing)** — use `differential_expression_by_gene`
- **Full detail rows with group framing** — use `expression_by_ortholog` script/skill
- **Group text search** — use `search_homolog_groups` first

## Status / Prerequisites

- [x] KG spec complete (no KG changes needed)
- [x] KG changes landed (N/A)
- [x] Scope reviewed with user
- [x] Result-size controls decided
- [x] Ready for Phase 2 (build)

## Use cases

- **Cross-organism expression triage** — "Do psbB orthologs respond
  to nitrogen stress across strains?" → check results per experiment × timepoint
- **Multi-group comparison** — "Compare expression signal for
  photosystem II vs nitrogen metabolism groups"

**Tool chains:**

| Tool | Role |
|---|---|
| `genes_by_homolog_group` | Groups → member genes (pure homology). |
| `differential_expression_by_gene` | Gene-centric expression. Single organism enforced. No group framing. |
| **`differential_expression_by_ortholog`** | Groups → expression at group × experiment × timepoint granularity across organisms. |
| `scripts/expression_by_ortholog.py` | Full workflow: membership + summary + per-organism detail rows. |

## KG dependencies

- `Gene` nodes: `locus_tag`, `gene_name`, `product`,
  `organism_strain`, `gene_category`
- `OrthologGroup` nodes: `id`, `consensus_gene_name`,
  `consensus_product`, `source`
- `Experiment` nodes: `id`, `name`, `treatment_type`, `treatment`,
  `omics_type`, `organism_strain`, `coculture_partner`,
  `table_scope`, `table_scope_detail`
- `Changes_expression_of` edges: `log2_fold_change`,
  `adjusted_p_value`, `expression_status`, `rank_by_effect`,
  `time_point`, `time_point_hours`, `time_point_order`
- `Gene_in_ortholog_group` edges (Gene → OrthologGroup)

No KG changes needed — all indexes exist (OrthologGroup.id,
Gene.organism_strain, Experiment.id).

---

## Tool Signature

```python
@mcp.tool(
    tags={"expression", "homology"},
    annotations={"readOnlyHint": True},
)
async def differential_expression_by_ortholog(
    ctx: Context,
    group_ids: Annotated[list[str], Field(
        description="Ortholog group IDs (from search_homolog_groups or "
        "gene_homologs). E.g. ['cyanorak:CK_00000570'].",
    )],
    organisms: Annotated[list[str] | None, Field(
        description="Filter by organisms (case-insensitive substring, "
        "OR semantics). E.g. ['MED4', 'MIT9313']. "
        "Use list_organisms to see valid values.",
    )] = None,
    experiment_ids: Annotated[list[str] | None, Field(
        description="Filter to these experiments. "
        "Get IDs from list_experiments.",
    )] = None,
    direction: Annotated[Literal["up", "down"] | None, Field(
        description="Filter by expression direction.",
    )] = None,
    significant_only: Annotated[bool, Field(
        description="If true, return only statistically significant rows.",
    )] = False,
    verbose: Annotated[bool, Field(
        description="If true, add experiment_name, treatment, omics_type, "
        "table_scope, table_scope_detail to each result row.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max result rows to return. Default 50.",
        ge=1, le=200,
    )] = 50,
) -> DifferentialExpressionByOrthologResponse:
    """Differential expression framed by ortholog groups.

    Cross-organism by design — results at group × experiment × timepoint
    granularity showing how many group members respond. Gene counts,
    not individual genes.

    Three list filters — each reports not_found + not_matched:
    - group_ids (required): ortholog groups
    - organisms: restrict to specific organisms
    - experiment_ids: restrict to specific experiments

    For group discovery, use search_homolog_groups first.
    For group membership without expression, use genes_by_homolog_group.
    For full detail rows, use the expression_by_ortholog skill.
    """
```

**Return envelope:** `{total_rows, matching_genes, matching_groups,
experiment_count, median_abs_log2fc, max_abs_log2fc, results,
returned, truncated, by_organism, rows_by_status,
rows_by_treatment_type, by_table_scope, top_groups, top_experiments,
not_found_groups, not_matched_groups, not_found_organisms,
not_matched_organisms, not_found_experiments, not_matched_experiments}`

**Per-result columns (compact):** group_id, consensus_gene_name,
consensus_product, experiment_id, treatment_type, organism_strain,
coculture_partner, timepoint, timepoint_hours, timepoint_order,
genes_with_expression, total_genes, significant_up,
significant_down, not_significant

**Verbose adds:** experiment_name, treatment, omics_type,
table_scope, table_scope_detail

## Result-size controls

Large result set — many groups × experiments × timepoints can
produce hundreds of rows.

**Sort key:** `group_id ASC, experiment_id ASC, timepoint_order ASC`

**Default limit:** 50

**Verbose:** yes — compact (15 fields) by default, verbose adds
5 experiment detail fields.

### Input validation

| Condition | Error |
|---|---|
| `group_ids` empty | `ValueError: group_ids must not be empty` |

## Special handling

**Multi-query orchestration:** 6 queries per invocation
(5 always, 1 conditional). All share the same WHERE helper.
Direct MATCH for results/top queries (efficient); OPTIONAL MATCH
for summary_global/diagnostics (needed for not_found/not_matched).

**total_genes join:** Q4 (results) can't compute total_genes
because it requires group members WITHOUT expression. Q5
(membership_counts) provides per group × organism member counts.
API layer joins on `(group_id, organism_strain)`.

**Organism filter semantics:** Unlike `differential_expression_by_gene`
which enforces single organism, this tool uses **OR semantics** across
organisms. The whole point is cross-organism comparison. When
`organisms` is None, all organisms are included.

**Expression filter precedence:** `direction` takes precedence over
`significant_only`. Same semantics as `differential_expression_by_gene`:
- `direction="up"` → `expression_status = "significant_up"`
- `direction="down"` → `expression_status = "significant_down"`
- `significant_only=True` → `expression_status <> "not_significant"`

**Batch handling — 6 diagnostic fields:**
Same semantics as `genes_by_homolog_group`:
- not_found = doesn't exist in KG (absolute)
- not_matched = exists but 0 results (contextual)
- Each input in at most one list
- None filters → empty lists

| Field | not_found | not_matched |
|---|---|---|
| `group_ids` | No OrthologGroup node | Group exists, 0 member genes have expression matching filters |
| `organisms` | No Gene nodes in KG matching name | Organism exists, 0 expression for group members |
| `experiment_ids` | No Experiment node in KG | Experiment exists, 0 expression edges to group member genes |

**Zero-match behavior:** When `total_rows=0`: all summary fields
present, counts are 0, breakdowns are empty. Each input appears in
either its not_found or not_matched list.

---

## Return envelope

```python
{
    "total_rows": 150,            # gene × experiment × timepoint rows
    "matching_genes": 5,          # distinct genes with expression
    "matching_groups": 2,         # distinct groups with expression
    "experiment_count": 3,
    "median_abs_log2fc": 1.2,     # median |log2FC| for significant rows
    "max_abs_log2fc": 4.5,        # max |log2FC| for significant rows
    "results": [
        {"group_id": "cyanorak:CK_00000570",
         "consensus_gene_name": "psbB",
         "consensus_product": "photosystem II chlorophyll-binding protein CP47",
         "experiment_id": "EXP001",
         "treatment_type": "nitrogen_limitation",
         "organism_strain": "Prochlorococcus MED4",
         "coculture_partner": null,
         "timepoint": "24h", "timepoint_hours": 24.0, "timepoint_order": 3,
         "genes_with_expression": 3, "total_genes": 5,
         "significant_up": 2, "significant_down": 1, "not_significant": 0},
        ...
    ],
    "returned": 18,
    "truncated": false,
    "by_organism": [{"organism": "Prochlorococcus MED4", "count": 60}, ...],
    "rows_by_status": {"significant_up": 30, "significant_down": 20,
                       "not_significant": 100},
    "rows_by_treatment_type": {"nitrogen_limitation": 80, "coculture": 70},
    "by_table_scope": {"all_detected_genes": 120, "significant_only": 30},
    "top_groups": [{"group_id": "cyanorak:CK_00000570",
                    "consensus_gene_name": "psbB",
                    "consensus_product": "photosystem II CP47",
                    "significant_genes": 4, "total_genes": 9}, ...],
    "top_experiments": [{"experiment_id": "EXP001",
                         "treatment_type": "nitrogen_limitation",
                         "organism_strain": "Prochlorococcus MED4",
                         "significant_genes": 12}, ...],
    "not_found_groups": [],
    "not_matched_groups": [],     # groups exist, 0 expression for members
    "not_found_organisms": [],
    "not_matched_organisms": [],  # organisms exist, 0 expression in groups
    "not_found_experiments": [],
    "not_matched_experiments": [], # experiments exist, 0 edges to group genes
}
```

`results` contains group × experiment × timepoint rows (capped by
`limit`). `returned` = len(results). `truncated` = total result rows
exceed `returned`.

### Summary fields

| Field | Type | Description |
|---|---|---|
| `total_rows` | int | Gene × experiment × timepoint rows matching all filters |
| `matching_genes` | int | Distinct genes with expression |
| `matching_groups` | int | Distinct groups with ≥1 gene having expression |
| `experiment_count` | int | Distinct experiments in results |
| `median_abs_log2fc` | float\|null | Median \|log2FC\| for significant rows |
| `max_abs_log2fc` | float\|null | Max \|log2FC\| for significant rows |
| `returned` | int | len(results) |
| `truncated` | bool | True if total result rows > returned |
| `by_organism` | list[dict] | `[{organism, count}]` — rows per organism, sorted desc |
| `rows_by_status` | dict | `{significant_up, significant_down, not_significant}` |
| `rows_by_treatment_type` | dict[str, int] | Row counts by treatment type |
| `by_table_scope` | dict[str, int] | Row counts by experiment table_scope (data completeness) |
| `top_groups` | list[dict] | Top 5 groups by significant gene count. `[{group_id, consensus_gene_name, consensus_product, significant_genes, total_genes}]` |
| `top_experiments` | list[dict] | Top 5 experiments by significant gene count. `[{experiment_id, treatment_type, organism_strain, significant_genes}]` |

### Per-result columns (compact — 15 fields)

One row per group × experiment × timepoint. Since experiments are
organism-specific, this naturally unpacks the cross-organism dimension.

| Field | Type | Description |
|---|---|---|
| `group_id` | str | Ortholog group ID |
| `consensus_gene_name` | str\|null | Short gene name (52% populated). Null for hypotheticals. |
| `consensus_product` | str | Group product description |
| `experiment_id` | str | Experiment ID |
| `treatment_type` | str | Treatment category |
| `organism_strain` | str | Organism (from experiment) |
| `coculture_partner` | str\|null | Coculture partner, if applicable |
| `timepoint` | str\|null | Timepoint label |
| `timepoint_hours` | float\|null | Numeric hours |
| `timepoint_order` | int | Sort key for time course |
| `genes_with_expression` | int | Group members with expression at this timepoint |
| `total_genes` | int | Total group members in this organism (computed from graph) |
| `significant_up` | int | Count |
| `significant_down` | int | Count |
| `not_significant` | int | Count |

### Verbose adds (5 fields)

| Field | Type | Description |
|---|---|---|
| `experiment_name` | str\|null | Human-readable experiment name |
| `treatment` | str\|null | Detailed treatment string |
| `omics_type` | str\|null | e.g. RNASEQ, PROTEOMICS |
| `table_scope` | str\|null | What genes the DE table contains |
| `table_scope_detail` | str\|null | Free-text clarification |

---

## Query Builder

**File:** `kg/queries_lib.py`

6 queries per invocation (5 always, 1 conditional). Q1–Q4 and Q6
share the same WHERE helper for consistent filtering. Q5
(membership_counts) uses a custom organism-only filter on
`g.organism_strain` since it has no expression edges. Direct MATCH
for results/top queries (efficient); OPTIONAL MATCH for
summary_global/diagnostics (needed for not_found/not_matched).

### Shared WHERE helper: `_differential_expression_by_ortholog_where`

```python
def _differential_expression_by_ortholog_where(
    *,
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[list[str], dict]:
    """Build WHERE conditions for differential_expression_by_ortholog builders.

    organisms: OR semantics on e.organism_strain (fuzzy word match).
    experiment_ids: e.id IN $experiment_ids.
    direction/significant_only: same as de_by_gene.

    Returns (conditions, params). Conditions are AND-joined into
    WHERE block by caller.
    """
```

**Conditions generated:**

| Parameter | Cypher condition |
|---|---|
| `organisms` | `ANY(org_input IN $organisms WHERE ALL(word IN split(toLower(org_input), ' ') WHERE toLower(e.organism_strain) CONTAINS word))` |
| `experiment_ids` | `e.id IN $experiment_ids` |
| `direction="up"` | `r.expression_status = "significant_up"` |
| `direction="down"` | `r.expression_status = "significant_down"` |
| `significant_only` | `r.expression_status <> "not_significant"` |

`direction` takes precedence over `significant_only`.

---

### Q1: `build_differential_expression_by_ortholog_summary_global`

Global aggregation + group-level not_found/not_matched. Single result row.

```python
def build_differential_expression_by_ortholog_summary_global(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """RETURN keys: total_rows, matching_genes, matching_groups,
    experiment_count, by_organism, rows_by_status,
    rows_by_treatment_type, by_table_scope,
    sig_log2fcs (list — API computes median/max),
    not_found_groups, not_matched_groups.
    """
```

```cypher
UNWIND $group_ids AS gid
OPTIONAL MATCH (og:OrthologGroup {id: gid})
OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og)
OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)
{where_block}
WITH gid, og, g, e, r
WITH collect(DISTINCT CASE WHEN og IS NULL THEN gid END) AS nf_raw,
     collect(DISTINCT CASE WHEN og IS NOT NULL THEN gid END) AS found_gids,
     collect(CASE WHEN r IS NOT NULL THEN {
       gid: gid, lt: g.locus_tag, org: e.organism_strain,
       status: r.expression_status, tt: e.treatment_type,
       ts: e.table_scope, eid: e.id,
       log2fc: r.log2_fold_change
     } END) AS rows_raw
WITH [x IN nf_raw WHERE x IS NOT NULL] AS not_found_groups,
     [r IN rows_raw WHERE r IS NOT NULL] AS rows,
     apoc.coll.toSet([x IN found_gids WHERE x IS NOT NULL]) AS found_gids
WITH not_found_groups,
     [gid IN found_gids
      WHERE NOT gid IN apoc.coll.toSet([r IN rows | r.gid])
     ] AS not_matched_groups,
     rows
RETURN size(rows) AS total_rows,
       size(apoc.coll.toSet([r IN rows | r.lt])) AS matching_genes,
       size(apoc.coll.toSet([r IN rows | r.gid])) AS matching_groups,
       size(apoc.coll.toSet([r IN rows | r.eid])) AS experiment_count,
       apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,
       apoc.coll.frequencies([r IN rows | r.status]) AS rows_by_status,
       apoc.coll.frequencies([r IN rows | r.tt]) AS rows_by_treatment_type,
       apoc.coll.frequencies([r IN rows | r.ts]) AS by_table_scope,
       not_found_groups, not_matched_groups,
       [r IN rows WHERE r.status <> "not_significant" | abs(r.log2fc)]
         AS sig_log2fcs
```

API layer computes `median_abs_log2fc` and `max_abs_log2fc` from
the `sig_log2fcs` list in Python (median via `statistics.median`,
max via `max`). This avoids the Neo4j limitation that
`percentileCont` is an aggregate function that operates on row
sets, not lists.

**Notes:**
- Uses `e.organism_strain` (from experiment, not gene) — consistent
  with the expression context.
- OPTIONAL MATCH chain needed for not_found/not_matched detection.
- All frequency/set operations use APOC, matching existing patterns.

---

### Q2: `build_differential_expression_by_ortholog_top_groups`

Top 5 groups by distinct significant genes. Separate query because
it needs GROUP BY group + ORDER BY + LIMIT which conflicts with
global aggregation.

```python
def build_differential_expression_by_ortholog_top_groups(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """RETURN keys: top_groups (list of maps)."""
```

```cypher
UNWIND $group_ids AS gid
MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})
MATCH (e:Experiment)-[r:Changes_expression_of]->(g)
{where_block}
WITH og,
     count(DISTINCT g.locus_tag) AS total_genes,
     count(DISTINCT CASE WHEN r.expression_status <> "not_significant"
                         THEN g.locus_tag END) AS significant_genes
ORDER BY significant_genes DESC, og.id ASC
LIMIT 5
RETURN collect({
  group_id: og.id,
  consensus_gene_name: og.consensus_gene_name,
  consensus_product: og.consensus_product,
  significant_genes: significant_genes,
  total_genes: total_genes
}) AS top_groups
```

**Notes:**
- Direct MATCH (no OPTIONAL) — groups with 0 expression don't appear,
  which is correct for ranking.
- `total_genes` here = genes in group that have expression matching
  filters, not all group members. Consistent with how `top_categories`
  works in de_by_gene.

---

### Q3: `build_differential_expression_by_ortholog_top_experiments`

Top 5 experiments by distinct significant genes across all groups.

```python
def build_differential_expression_by_ortholog_top_experiments(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """RETURN keys: top_experiments (list of maps)."""
```

```cypher
UNWIND $group_ids AS gid
MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})
MATCH (e:Experiment)-[r:Changes_expression_of]->(g)
{where_block}
WITH e,
     count(DISTINCT CASE WHEN r.expression_status <> "not_significant"
                         THEN g.locus_tag END) AS significant_genes
ORDER BY significant_genes DESC, e.id ASC
LIMIT 5
RETURN collect({
  experiment_id: e.id,
  treatment_type: e.treatment_type,
  organism_strain: e.organism_strain,
  significant_genes: significant_genes
}) AS top_experiments
```

---

### Q4: `build_differential_expression_by_ortholog_results`

Results at group × experiment × timepoint granularity. Main detail query.

```python
def build_differential_expression_by_ortholog_results(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    verbose: bool = False,
    limit: int = 50,
) -> tuple[str, dict]:
    """RETURN keys: one row per group × experiment × timepoint.

    Compact: group_id, consensus_gene_name, consensus_product,
    experiment_id, treatment_type, organism_strain, coculture_partner,
    timepoint, timepoint_hours, timepoint_order,
    genes_with_expression, significant_up, significant_down,
    not_significant.

    Verbose adds: experiment_name, treatment, omics_type,
    table_scope, table_scope_detail.

    total_genes joined from Q5 in API layer.
    """
```

```cypher
UNWIND $group_ids AS gid
MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})
MATCH (e:Experiment)-[r:Changes_expression_of]->(g)
{where_block}
WITH og, e,
     r.time_point AS tp,
     r.time_point_hours AS tph,
     r.time_point_order AS tpo,
     collect(DISTINCT g.locus_tag) AS genes,
     collect(r.expression_status) AS statuses
RETURN og.id AS group_id,
       og.consensus_gene_name AS consensus_gene_name,
       og.consensus_product AS consensus_product,
       e.id AS experiment_id,
       e.treatment_type AS treatment_type,
       e.organism_strain AS organism_strain,
       e.coculture_partner AS coculture_partner,
       tp AS timepoint,
       tph AS timepoint_hours,
       tpo AS timepoint_order,
       size(genes) AS genes_with_expression,
       size([s IN statuses WHERE s = "significant_up"]) AS significant_up,
       size([s IN statuses WHERE s = "significant_down"]) AS significant_down,
       size([s IN statuses WHERE s = "not_significant"]) AS not_significant
       {verbose_fields}
ORDER BY og.id ASC, e.id ASC, tpo ASC
LIMIT $limit
```

Where `{verbose_fields}` conditionally adds:
```cypher
       , e.name AS experiment_name
       , e.treatment AS treatment
       , e.omics_type AS omics_type
       , e.table_scope AS table_scope
       , e.table_scope_detail AS table_scope_detail
```

**Notes:**
- Direct MATCH — no OPTIONAL needed (groups/experiments with no
  results simply produce no rows).
- GROUP BY is implicit via `WITH og, e, tp, tph, tpo` — one row
  per group × experiment × timepoint.
- `genes` is `collect(DISTINCT g.locus_tag)` — counts distinct
  genes, not duplicate expression edges.
- `statuses` is `collect(r.expression_status)` (not DISTINCT) —
  one status per gene, so `significant_up + significant_down +
  not_significant = genes_with_expression`.
- `total_genes` is NOT computed here — it needs group members
  without expression, which this MATCH can't see. Joined from Q5.

**Variable scoping check:** `og` and `e` are carried through the
single WITH clause. `tp`, `tph`, `tpo` are derived from `r` in the
same WITH. No downstream variables are dropped.

---

### Q5: `build_differential_expression_by_ortholog_membership_counts`

Per group × organism member counts (including genes without
expression). Lightweight query — no expression edges.

```python
def build_differential_expression_by_ortholog_membership_counts(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
    """RETURN keys: group_id, organism_strain, total_genes."""
```

```cypher
UNWIND $group_ids AS gid
MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})
WHERE ($organisms IS NULL OR ANY(org_input IN $organisms
       WHERE ALL(word IN split(toLower(org_input), ' ')
             WHERE toLower(g.organism_strain) CONTAINS word)))
RETURN og.id AS group_id,
       g.organism_strain AS organism_strain,
       count(g) AS total_genes
```

**Does NOT use the shared WHERE helper** — that helper references
`e.organism_strain` and `r.expression_status`, but Q5 has no
expression edges. Organism filter is applied directly on
`g.organism_strain`.

**API layer join:** For each result row from Q4, look up
`total_genes` by `(group_id, organism_strain)` from Q5 results.

**Notes:**
- Can't use pre-computed `og.member_count` — that's group-wide
  across all organisms. We need per-organism counts, further
  restricted by organism filter.
- Only uses `organisms` filter (not direction/significant_only/
  experiment_ids) — total_genes means all group members in that
  organism, not just those with matching expression.

---

### Q6: `build_differential_expression_by_ortholog_diagnostics`

Validates organisms + experiment_ids (not_found vs not_matched).
Same pattern as `genes_by_homolog_group` diagnostics.

```python
def build_differential_expression_by_ortholog_diagnostics(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict] | None:
    """Returns None when both organisms and experiment_ids are None.

    RETURN keys: not_found_organisms, not_matched_organisms,
    not_found_experiments, not_matched_experiments.
    """
```

#### Organism validation:

```cypher
WITH $organisms AS org_inputs
UNWIND CASE WHEN org_inputs IS NULL THEN [null]
       ELSE org_inputs END AS org_input
OPTIONAL MATCH (g_any:Gene)
WHERE org_input IS NOT NULL
  AND ALL(word IN split(toLower(org_input), ' ')
          WHERE toLower(g_any.organism_strain) CONTAINS word)
WITH org_input, count(g_any) AS kg_count
OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup)
WHERE org_input IS NOT NULL AND kg_count > 0
  AND og.id IN $group_ids
  AND ALL(word IN split(toLower(org_input), ' ')
          WHERE toLower(g.organism_strain) CONTAINS word)
OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)
{expression_where}
WITH org_input, kg_count, count(r) AS matched_count
WITH collect(CASE WHEN org_input IS NOT NULL AND kg_count = 0
                  THEN org_input END) AS nf_raw,
     collect(CASE WHEN org_input IS NOT NULL AND kg_count > 0
                  AND matched_count = 0 THEN org_input END) AS nm_raw
RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_organisms,
       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_organisms
```

#### Experiment validation:

```cypher
WITH $experiment_ids AS eid_inputs
UNWIND CASE WHEN eid_inputs IS NULL THEN [null]
       ELSE eid_inputs END AS eid
OPTIONAL MATCH (e:Experiment {id: eid})
WITH eid, e, CASE WHEN e IS NULL THEN true ELSE false END AS missing
OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)
            -[:Gene_in_ortholog_group]->(og:OrthologGroup)
WHERE NOT missing AND og.id IN $group_ids
{organism_and_expression_where}
WITH eid, missing, count(r) AS matched_count
WITH collect(CASE WHEN missing THEN eid END) AS nf_raw,
     collect(CASE WHEN NOT missing AND matched_count = 0
                  THEN eid END) AS nm_raw
RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_experiments,
       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_experiments
```

**Notes:**
- Organism and experiment validation can be combined into one query
  or run as two — implementation choice. Two is simpler.
- Returns None (skips query) when both filters are None — avoids
  unnecessary round-trip. API layer fills empty lists.

---

## API Function

**File:** `api/functions.py`

```python
def differential_expression_by_ortholog(
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    verbose: bool = False,
    limit: int = 50,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Differential expression framed by ortholog groups.

    Returns dict with keys: total_rows, matching_genes, matching_groups,
    results, returned, truncated, by_organism, rows_by_status,
    rows_by_treatment_type, by_table_scope, top_groups, top_experiments,
    experiment_count, median_abs_log2fc, max_abs_log2fc,
    not_found_groups, not_matched_groups, not_found_organisms,
    not_matched_organisms, not_found_experiments, not_matched_experiments.

    Raises:
        ValueError: if group_ids is empty.
    """
```

**Query orchestration (up to 6 queries):**

| Query | Builder | Always run? |
|---|---|---|
| Q1 summary_global | `build_..._summary_global` | Yes |
| Q2 top_groups | `build_..._top_groups` | Yes |
| Q3 top_experiments | `build_..._top_experiments` | Yes |
| Q4 results | `build_..._results` | Yes |
| Q5 membership_counts | `build_..._membership_counts` | Yes |
| Q6 diagnostics | `build_..._diagnostics` | Only when organisms or experiment_ids provided |

**API assembly:**
1. Run Q1–Q5 (and Q6 if needed). Q1–Q5 are independent — can
   be submitted concurrently if driver supports it.
2. Join Q5 `total_genes` into Q4 result rows on
   `(group_id, organism_strain)`.
3. Merge Q1 summary fields + Q2 top_groups + Q3 top_experiments
   + Q4 results (with total_genes) + Q6 diagnostics into
   response dict.
4. Set `returned = len(results)`, `truncated = total result rows
   exceed returned`.

**Notes:**
- No single-organism enforcement (cross-organism is the point)
- `total_rows` from Q1 counts gene × experiment × timepoint
  edges (before grouping); `returned` counts result rows
  (after grouping by group × experiment × timepoint)

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
class DifferentialExpressionByOrthologResult(BaseModel):
    # --- always present ---
    group_id: str
    consensus_gene_name: str | None
    consensus_product: str
    experiment_id: str
    treatment_type: str
    organism_strain: str
    coculture_partner: str | None
    timepoint: str | None
    timepoint_hours: float | None
    timepoint_order: int
    genes_with_expression: int = Field(
        description="Group members with expression at this timepoint")
    total_genes: int = Field(
        description="Total group members in this organism (computed)")
    significant_up: int
    significant_down: int
    not_significant: int
    # --- verbose only ---
    experiment_name: str | None = Field(None, description="Verbose only")
    treatment: str | None = Field(None, description="Verbose only")
    omics_type: str | None = Field(None, description="Verbose only")
    table_scope: str | None = Field(None, description="Verbose only")
    table_scope_detail: str | None = Field(None, description="Verbose only")

class DifferentialExpressionByOrthologTopGroup(BaseModel):
    group_id: str
    consensus_gene_name: str | None
    consensus_product: str
    significant_genes: int
    total_genes: int

class DifferentialExpressionByOrthologTopExperiment(BaseModel):
    experiment_id: str
    treatment_type: str
    organism_strain: str
    significant_genes: int

class DifferentialExpressionByOrthologResponse(BaseModel):
    total_rows: int
    matching_genes: int
    matching_groups: int
    experiment_count: int
    median_abs_log2fc: float | None
    max_abs_log2fc: float | None
    results: list[DifferentialExpressionByOrthologResult]
    returned: int
    truncated: bool
    by_organism: list[dict]   # [{organism, count}]
    rows_by_status: dict      # {significant_up, significant_down, not_significant}
    rows_by_treatment_type: dict[str, int]
    by_table_scope: dict[str, int]
    top_groups: list[DifferentialExpressionByOrthologTopGroup]
    top_experiments: list[DifferentialExpressionByOrthologTopExperiment]
    not_found_groups: list[str] = Field(default_factory=list)
    not_matched_groups: list[str] = Field(default_factory=list)
    not_found_organisms: list[str] = Field(default_factory=list)
    not_matched_organisms: list[str] = Field(default_factory=list)
    not_found_experiments: list[str] = Field(default_factory=list)
    not_matched_experiments: list[str] = Field(default_factory=list)
```

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `_differential_expression_by_ortholog_where` + Q1–Q6 builders |
| 2 | API function | `api/functions.py` | `differential_expression_by_ortholog()` |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | Pydantic models + `@mcp.tool()` wrapper |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildDifferentialExpressionByOrtholog*` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `TestDifferentialExpressionByOrtholog` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestDifferentialExpressionByOrthologWrapper` + update `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Smoke test against live KG |
| 9 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | Add cases |
| 11 | About content | `multiomics_explorer/inputs/tools/differential_expression_by_ortholog.yaml` | Input YAML |
| 12 | Docs | `CLAUDE.md` | Add row to MCP Tools table |
| 13 | Code review | — | Run code-review skill |

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildDifferentialExpressionByOrthologSummaryGlobal:
    test_single_group
    test_multiple_groups
    test_organisms_filter
    test_experiment_ids_filter
    test_direction_filter
    test_significant_only
    test_returns_expected_keys
    test_rows_by_treatment_type
    test_by_table_scope
    test_not_found_groups
    test_not_matched_groups

class TestBuildDifferentialExpressionByOrthologTopGroups:
    test_top_5_by_significant_genes
    test_tiebreak_by_group_id
    test_filters_applied

class TestBuildDifferentialExpressionByOrthologTopExperiments:
    test_top_5_by_significant_genes
    test_tiebreak_by_experiment_id
    test_filters_applied

class TestBuildDifferentialExpressionByOrthologResults:
    test_group_x_experiment_x_timepoint_rows
    test_status_counts_per_row
    test_verbose_fields
    test_limit

class TestBuildDifferentialExpressionByOrthologMembershipCounts:
    test_per_group_per_organism
    test_includes_genes_without_expression
    test_organism_filter_only

class TestBuildDifferentialExpressionByOrthologDiagnostics:
    test_organisms_not_found_vs_not_matched
    test_experiments_not_found_vs_not_matched
    test_none_returns_none
```

### Unit: API function (`test_api_functions.py`)

```
class TestDifferentialExpressionByOrtholog:
    test_returns_dict
    test_passes_params
    test_empty_group_ids_raises
    test_results_assembly
    test_total_genes_join
    test_returned_truncated
    test_top_groups_and_top_experiments
    test_six_diagnostic_fields
    test_creates_conn_when_none
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestDifferentialExpressionByOrthologWrapper:
    test_returns_dict_envelope
    test_empty_results
    test_params_forwarded
    test_truncation_metadata
    test_results_row_model
    test_not_found_and_not_matched

Update EXPECTED_TOOLS to include "differential_expression_by_ortholog".
```

### Integration (`test_mcp_tools.py`)

Against live KG:
- Single group → results with group × experiment × timepoint rows
- Multiple groups → results from all groups
- Organisms filter reduces by_organism and results
- Experiment filter reduces experiment_count and results
- direction="up" → rows_by_status only has significant_up
- Fake group → not_found_groups
- Group with no expression members → not_matched_groups
- genes_with_expression <= total_genes in each result row
- Verbose adds experiment_name, treatment, omics_type, table_scope

### Eval cases (`cases.yaml`)

```yaml
- id: differential_expression_by_ortholog_basic
  tool: differential_expression_by_ortholog
  desc: Single group expression across organisms
  params:
    group_ids: ["cyanorak:CK_00000570"]
  expect:
    has_keys: [total_rows, matching_genes, results, returned,
               by_organism, rows_by_status, top_groups, top_experiments]

- id: differential_expression_by_ortholog_organism_filter
  tool: differential_expression_by_ortholog
  desc: Group expression for specific organisms
  params:
    group_ids: ["cyanorak:CK_00000570"]
    organisms: ["MED4", "MIT9313"]
  expect:
    has_keys: [total_rows, results, returned, by_organism]

- id: differential_expression_by_ortholog_significant
  tool: differential_expression_by_ortholog
  desc: Only significant expression
  params:
    group_ids: ["cyanorak:CK_00000570"]
    significant_only: true
  expect:
    has_keys: [total_rows, results, returned, rows_by_status]
```

---

## About Content

### Input YAML

**File:** `multiomics_explorer/inputs/tools/differential_expression_by_ortholog.yaml`

Create with `uv run python scripts/build_about_content.py --skeleton differential_expression_by_ortholog`,
then fill in examples, chaining, mistakes.

```yaml
examples:
  - title: Expression across orthologs in a group
    call: differential_expression_by_ortholog(group_ids=["cyanorak:CK_00000570"])

  - title: Compare two groups in specific organisms
    call: differential_expression_by_ortholog(group_ids=["cyanorak:CK_00000570", "eggnog:COG0592@2"], organisms=["MED4", "MIT9313"])

  - title: Full pipeline from text to expression
    steps: |
      Step 1: search_homolog_groups(search_text="photosystem II")
              → collect group_ids

      Step 2: differential_expression_by_ortholog(group_ids=[...],
                organisms=["MED4", "MIT9313"])
              → triage: which groups have expression?

      Step 3 (if detail needed): use expression_by_ortholog script

verbose_fields:
  - experiment_name
  - treatment
  - omics_type
  - table_scope
  - table_scope_detail

chaining:
  - "search_homolog_groups → differential_expression_by_ortholog"
  - "gene_homologs → differential_expression_by_ortholog"
  - "genes_by_homolog_group (triage) → differential_expression_by_ortholog"
  - "differential_expression_by_ortholog → scripts/expression_by_ortholog.py (detail)"

mistakes:
  - "group_ids must be full IDs with prefix (e.g. 'cyanorak:CK_00000570')"
  - "organisms is a list, not a string — use ['MED4'] not 'MED4'"
  - "This tool does NOT enforce single organism — that is the point"
  - "Results are group × experiment × timepoint (gene counts), not individual genes. Use the script for per-gene detail."
```

### Build

```bash
uv run python scripts/build_about_content.py differential_expression_by_ortholog
```

**Output:** `multiomics_explorer/skills/multiomics-kg-guide/references/tools/differential_expression_by_ortholog.md`

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Comparison: differential_expression_by_ortholog vs differential_expression_by_gene

### Inputs

| Parameter | differential_expression_by_ortholog | differential_expression_by_gene |
|---|---|---|
| Primary input | `group_ids: list[str]` | At least one of organism/locus_tags/experiment_ids |
| Organism | `organisms: list[str]\|None` — OR semantics, cross-organism | `organism: str\|None` — single, enforced |
| Experiment | `experiment_ids: list[str]\|None` | `experiment_ids: list[str]\|None` |
| Gene | — (from group membership) | `locus_tags: list[str]\|None` |
| Expression filters | `direction`, `significant_only` | `direction`, `significant_only` |
| Detail controls | `verbose`, `limit` | `summary`, `verbose`, `limit` |

### Output

| Field | differential_expression_by_ortholog | differential_expression_by_gene |
|---|---|---|
| Row count | `total_rows` | `total_rows` |
| Gene count | `matching_genes` | `matching_genes` |
| Group dimension | `results` (group × experiment × timepoint rows) | — |
| Organism dimension | `by_organism` [{organism, count}] | — (single organism) |
| Status | `rows_by_status` | `rows_by_status` |
| Effect stats | `median_abs_log2fc`, `max_abs_log2fc` | same |
| Treatment | `rows_by_treatment_type` | `rows_by_treatment_type` |
| Table scope | `by_table_scope` | `by_table_scope` |
| Top N triage | `top_groups` (top 5), `top_experiments` (top 5) | `top_categories` (top 5) |
| Experiment | `experiment_count` | `experiment_count` + `experiments` (nested) |
| Diagnostics | 6 fields (not_found/not_matched × 3 filters) | `not_found` + `no_expression` |
| Detail rows | per group × experiment × timepoint (gene counts) | per gene × experiment × timepoint (individual genes) |

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add row: `differential_expression_by_ortholog` — "Differential expression framed by ortholog groups. Cross-organism. Results at group × experiment × timepoint granularity (gene counts, not individual genes). Summary: by_organism, rows_by_status, rows_by_treatment_type, by_table_scope, top_groups, top_experiments. Batch: not_found/not_matched for groups, organisms, experiments. Filterable by organisms, experiment_ids, direction, significant_only." |
