# Plan: Publications, experiments, and expression — full KG + MCP redesign

## The three layers

Researchers navigate expression data as **Publication → Experiment → Results**.
The KG and MCP tools should mirror this directly.

### Layer 1: Publication — "What studies exist?"

21 Publication nodes already exist with title, abstract, authors, DOI. But
they're invisible to Claude — no MCP tool surfaces them.

### Layer 2: Experiment — "What was tested?"

This is the missing layer. An experiment is the biological question: one
organism, one perturbation, one control, one omics platform — possibly across
multiple time points (a **time series**). The paperconfig `statistical_analyses`
entries already define these, but the KG flattens them onto edge properties.

~180 analyses exist across 24 papers. Many form natural time series:
- Lindell 2007: phage infection at 1h–8h (8 time points)
- Tolonen 2006: N deprivation at 0h–48h (6 time points)
- Coe 2024: diel cycle at 0h–24h (7 time points)
- Weissberg 2025: starvation from day 11 to day 89 (5+ time points,
  both RNA-seq and proteomics)

Currently time series aren't represented — each time point is an independent
edge with no grouping. Worse, some paperconfigs embed the time point into
`treatment_condition` text, preventing even post-hoc grouping.

### Layer 3: Results — "What changed?"

Per-gene log2FC/padj/direction within an experiment at a specific time point.
The current tools return only this layer, stripped of context, drowning in
non-significant results.

---

## KG redesign

### New node: `Experiment`

One node per biological time series (or single-point comparison). Groups
paperconfig analyses that share the same scientific question but differ only
in time point.

**Properties:**

| Property | Source | Example |
|---|---|---|
| `id` | `{doi}_{experiment_group_id}` — see ID stability note below | `doi:10.1038/ismej.2016.70_coculture_vs_axenic_MED4` |
| `name` | Human-readable description | `"MED4 response to coculture with HOT1A3"` |
| `organism_strain` | `organism` | `"Prochlorococcus MED4"` |
| `treatment_type` | from paperconfig `experiments` block | `"nitrogen_stress"`, `"coculture"` |
| `treatment` | `treatment_condition` (time-point stripped) | `"Coculture with Alteromonas HOT1A3"` |
| `control` | `control_condition` | `"Axenic"` |
| `experimental_context` | `experimental_context` | `"in Pro99 medium under continuous light"` |
| `coculture_partner` | from `treatment_organism` (null for environmental) | `"Alteromonas macleodii HOT1A3"` |
| `omics_type` | `type` | `"RNASEQ"` |
| `statistical_test` | `test_type` | `"DESeq2"` |
| `is_time_course` | computed: >1 time point | `true` |
| `medium` | growth medium | `"Pro99"`, `"PRO99-lowN"` |
| `temperature` | growth temperature | `"24C"` |
| `light_condition` | light regime | `"continuous_light"`, `"13:11 light:dark cycle"` |
| `light_intensity` | PAR intensity | `"30 umol photons m-2 s-1"` |

**Property naming note:** The KG stores `treatment_type` (matching the
paperconfig field name). MCP tools expose this as the `condition_type`
parameter — a more intuitive name for the LLM. The mapping
`condition_type` (MCP) → `treatment_type` (Neo4j) happens in the tool layer.

Note: `gene_count`, `significant_count`, per-time-point stats are **not**
stored on the node — they are computed at query time from
`Changes_expression_of` edges by the MCP tool layer. This avoids data
duplication and staleness. The Experiment node stays lean with only metadata
that comes from the paperconfig.

Note: `treatment_type` (exposed to the LLM as `condition_type`) unifies
environmental and coculture experiments into one filterable dimension. For
environmental experiments it comes from the paperconfig (e.g.
`"nitrogen_stress"`, `"light_stress"`). For coculture experiments it's
`"coculture"`. This means the LLM filters the same way regardless of
experiment type — no need to understand the coculture-vs-environmental split.

**Experiment node ID stability:** The `experiment_group_id` component should
come from an explicit `experiment_group_id` field in the paperconfig, not be
derived from the grouping rule. This prevents ID changes when treatment text
or context strings are cleaned up. The adapter generates a default group ID
from the grouping key if not explicitly provided, but paperconfigs should
declare it explicitly for stability. Format: short deterministic slug,
e.g. `coculture_vs_axenic_MED4`, `n_starvation_axenic_HOT1A3_rnaseq`.

**Grouping rule:** Paperconfig analyses with the same `experiment_group_id`
(or, if absent, the same {organism, treatment, control, experimental_context,
omics_type}) belong to the same Experiment. The explicit ID is preferred;
automatic grouping is a convenience fallback. **The adapter should log a
warning when auto-grouping fires** — silent grouping could produce unexpected
experiment boundaries if a paperconfig is missing the field.

### New edges

| Edge | From | To | Properties |
|---|---|---|---|
| `Has_experiment` | Publication | Experiment | — |
| `Tests_coculture_with` | Experiment | OrganismTaxon | coculture only |

### Redesigned expression edges

**Current:** `Factor → Gene` with all metadata on the edge.

**New:** `Experiment -[Changes_expression_of]-> Gene`

Reads naturally: "Experiment changes expression of Gene." Unifies the two old
edge labels (`Condition_changes_expression_of`, `Coculture_changes_expression_of`)
— the source is always Experiment now, so the condition/coculture prefix is gone.

Edge properties (per gene, per time point):

| Property | Type |
|---|---|
| `time_point` | string — original label (null for single-point experiments) |
| `time_point_order` | int — ordinal position in the series (1-indexed) |
| `time_point_hours` | float — normalized to hours (nullable if unparseable) |
| `log2_fold_change` | float |
| `adjusted_p_value` | float (nullable) |
| `expression_direction` | `"up"` / `"down"` |
| `significant` | `"significant"` / `"not significant"` / `"unknown"` |
| `rank_by_effect` | int — rank by \|log2FC\| within experiment+timepoint (1 = largest) |

That's it. Everything else (organism, treatment, control, context, omics type,
publication) lives on the Experiment or Publication node. No more duplicating
metadata across thousands of edges.

`rank_by_effect` is computed post-import: rank each gene by absolute fold-change
within each experiment + timepoint. Gives the LLM instant context: "PMM0120 is
the 15th most changed gene (out of 1696) in this experiment at this timepoint."

For time-course experiments, a single gene has multiple parallel edges from
the same Experiment node — one per time point, distinguished by `time_point`.

**Time-course edge cardinality note:** A time course with 8 time points and
2000 genes produces 16,000 parallel edges from one Experiment node. Neo4j
handles this fine, but the MCP tool needs to be careful about limits — see
the `query_expression` limit discussion below.

### EnvironmentalCondition — absorbed into Experiment

The current graph has ~40 EnvironmentalCondition nodes linked to expression
edges. The KG redesign **merges these into the Experiment node**:

1. Already pub-scoped (no cross-paper reuse)
2. Structured properties sparsely populated and rarely queried
3. The key filterable property (`treatment_type`) is on Experiment regardless
4. Eliminates a node type + edge type → simpler graph

Experimental context fields (`medium`, `temperature`, `light_condition`,
`light_intensity`) move directly onto the Experiment node.

### Graph structure

```
Publication ──Has_experiment──> Experiment ──Changes_expression_of──> Gene
                                    │
                                    └──Tests_coculture_with──> OrganismTaxon
                                       (coculture experiments only)
```

### Nodes retained as-is

- **Publication** — already exists, no changes needed
- **OrganismTaxon** — still the target of `Tests_coculture_with`
- **Gene** — still the target of expression edges

### Nodes removed

- **EnvironmentalCondition** — absorbed into Experiment

### Edges removed

- `Condition_changes_expression_of` — replaced by `Changes_expression_of`
- `Coculture_changes_expression_of` — replaced by `Changes_expression_of`
- `Published_expression_data_about` — replaced by `Has_experiment`

### Why the expression edge source changes to Experiment

Currently `Factor → Gene` encodes "this condition/organism caused this change."
But the causal factor is really a property of the experiment, not of each
individual gene result. Moving the edge to `Experiment → Gene` means:

- The Experiment node carries the full context (what was tested, what was the
  control, what organism, what platform)
- The edge carries only per-gene, per-timepoint data (FC, p-value, direction,
  rank)
- Querying "what genes changed in this experiment?" is a 1-hop query
- Querying "what experiments affected this gene?" is a 1-hop query
- Querying "what genes respond to nitrogen stress?" is 1-hop:
  `(e:Experiment {treatment_type: "nitrogen_stress"})-[r:Changes_expression_of]->(g:Gene)`
  (no join needed — `treatment_type` is on Experiment)

---

## MCP tools

### `list_publications` (new)

```
list_publications(
    organism: str | None,        # matches organism_strain OR coculture_partner
    condition_type: str | None,  # "coculture", "nitrogen_stress", etc.
    keyword: str | None,         # free-text on title/abstract
) -> Publication metadata + experiment summaries
```

Surfaces the 21 Publication nodes. Returns: title, authors, DOI, abstract,
study_type, and a summary of experiments contributed (count, organisms,
condition types, omics types). Uses `HAS_EXPERIMENT` to compute stats.

**Example queries the LLM would make:**
- "What papers study Prochlorococcus MED4?" → `organism="MED4"`
- "What coculture papers exist?" → `condition_type="coculture"`
- "Papers about nitrogen?" → `keyword="nitrogen"`

### `list_experiments` (new)

```
list_experiments(
    publication: str | None,         # DOI or keyword on publication title
    organism: str | None,            # matches organism_strain OR coculture_partner
    condition_type: str | None,      # "coculture", "nitrogen_stress", etc.
    coculture_partner: str | None,   # partner organism only (narrows coculture)
    omics_type: str | None,          # RNASEQ, PROTEOMICS, MICROARRAY
    keyword: str | None,             # free-text on experiment name/treatment/
                                     #   control/experimental_context
    time_course_only: bool = False,
) -> Experiment metadata with time points and gene counts
```

Returns one row per Experiment: id, name, publication DOI, organism,
condition_type, treatment, control, coculture_partner, omics_type,
is_time_course, time_points (with per-time-point significant/total counts),
gene_count, significant_count.

Per-time-point stats and gene counts are computed at query time by
aggregating `Changes_expression_of` edges grouped by `time_point_order`. This keeps the
Experiment node lean while giving the LLM rich summary data.

**Query cost note:** `list_experiments` with no filters aggregates across all
~188K `Changes_expression_of` edges. This should be sub-second for Neo4j with
proper indexing. If it ever gets slow, these stats could be
cached as post-import computed properties, but that's premature optimization.

For time courses, the per-time-point stats let the LLM compare stress
trajectories (significant counts over time) between experiments directly,
without pulling gene-level data.

This is the routing tool — browse the experimental landscape, then use
experiment IDs with `query_expression`.

**Example queries the LLM would make:**
- "What experiments exist for MED4?" → `organism="MED4"`
- "Coculture experiments with Alteromonas?" → `condition_type="coculture", coculture_partner="Alteromonas"`
- "Experiments under continuous light?" → `keyword="continuous light"`
- "Experiments comparing diel cycle?" → `keyword="diel"`
- "What nitrogen stress time courses exist?" → `condition_type="nitrogen_stress", time_course_only=True`
- "What proteomics data do we have?" → `omics_type="PROTEOMICS"`
- "Experiments from Biller 2018?" → `publication="Biller 2018"`

The `keyword` parameter does CONTAINS matching across the experiment's name,
treatment, control, and experimental_context fields. This catches queries
about experimental details (light regime, medium, temperature) that don't
have dedicated structured filters.

### `query_expression` (redefined)

```
query_expression(
    experiment_id: str | None,       # from list_experiments
    gene_ids: list[str] | None,      # locus_tags
    include_orthologs: bool = False, # expand gene_ids via OrthologGroup
    organism: str | None,            # when querying by gene across experiments
    condition_type: str | None,      # filter experiments by condition type
    time_points: list[str] | None,   # filter specific time points
    direction: str | None,           # "up" or "down"
    min_log2fc: float | None,
    max_pvalue: float | None,
    significant_only: bool | None,   # default depends on mode — see below
    limit: int = 100,
) -> Gene-level DE results
```

At least one of `experiment_id` or `gene_ids` must be provided. Calling with
only broad filters (e.g., `condition_type="nitrogen_stress"`) without either
would return thousands of rows — the tool requires at least one anchor.

Two primary modes:

**Experiment-centric:** provide `experiment_id` → get all significant genes
for that experiment. If time course, results include time_point column.
Optionally filter to specific `time_points`.
Default: `significant_only=True` — you want the highlights.

**Gene-centric:** provide `gene_ids` → get all experiments where those genes
have results. Optionally filter by `organism`, `condition_type`, `direction`,
etc. Returns experiment name + publication DOI for context.
Default: `significant_only=False` — "this gene didn't respond to nitrogen
stress" is informative. Absence of response is a result.

When `significant_only` is not explicitly set, the tool infers the default
from the query mode: True if `experiment_id` is provided without `gene_ids`,
False if `gene_ids` is provided. If both are provided, defaults to True
(experiment-scoped gene lookup).

**Ortholog expansion (gene-centric mode only):** when `include_orthologs=True`, the tool internally
resolves orthologs for each input gene (via OrthologGroup), then queries
expression for the full set. Results include an `ortholog_group` column so
the LLM can compare across strains. The expansion happens in the tool
wrapper (not Cypher) — it calls the homolog lookup, collects locus_tags,
then runs the expression query for all of them. If expanded orthologs have
no expression data (no matching experiments for those strains), the response
includes a warning: "Orthologs found in MIT9313, NATL2A but no expression
experiments exist for those strains." This avoids silent empty results. When `experiment_id` is provided,
`include_orthologs` is silently ignored — an experiment is single-organism,
so ortholog expansion is meaningless.

**Limit behavior for time courses:** The `limit` applies per-gene (not
per-row). For an experiment with 8 time points, `limit=100` returns up to
100 genes × 8 time points = 800 rows. This prevents a time course from
burning the entire limit on the first ~12 genes. Implementation: query with
`LIMIT $limit` on distinct genes, then fetch all time points for those genes.

Return columns: gene, product, organism_strain, experiment_id, experiment_name,
publication_doi, condition_type, time_point, direction, log2fc, padj,
rank_by_effect (rank by |log2FC| within experiment+timepoint, 1 = largest).
When `include_orthologs=True`, also: ortholog_group, query_gene (the original
input gene that this ortholog was expanded from).

**Example queries the LLM would make:**
- "What genes are upregulated in this experiment?" → `experiment_id="...", direction="up"`
- "Show me PMM0120 across all experiments" → `gene_ids=["PMM0120"]`
- "Is PMM0120 affected by nitrogen stress?" → `gene_ids=["PMM0120"], condition_type="nitrogen_stress"`
- "What are the photosynthesis genes doing at 1h vs 24h?" → `experiment_id="...", gene_ids=[...], time_points=["1h", "24h"]`
- "Is the nitrogen response of PMM0120 conserved across strains?" → `gene_ids=["PMM0120"], include_orthologs=True, condition_type="nitrogen_stress"`
- "Do all Pro strains upregulate this gene in coculture?" → `gene_ids=["PMM0120"], include_orthologs=True, condition_type="coculture"`

### `compare_conditions` — removed

Merged into `query_expression`. Passing multiple `gene_ids` without an
`experiment_id` gives you the cross-experiment comparison. Claude organizes
the output.

---

## Paperconfig changes (KG-side, detailed in KG plan)

The KG plan (`multiomics_biocypher_kg/plans/experiment_node_redesign.md`)
covers paperconfig changes in full detail. Summary of what changes:

- **New `experiments` block** as a first-class section in each paperconfig.
  Defines experiment-level metadata (organism, treatment, control, omics_type,
  treatment_type, medium, temperature, light_condition, light_intensity).
- **`environmental_conditions` block removed** — absorbed into experiments.
- **Analyses reference experiments** via `experiment:` key instead of
  repeating shared fields.
- **`timepoint_hours`** added to each analysis (explicit numeric).
- **`treatment_condition` time-stripped** across all paperconfigs.
- **Migration script** automates conversion of all 26 paperconfigs.

---

## Implementation

### Phase 1: Core DE redesign (KG + Explorer)

| Step | What | Where |
|---|---|---|
| 1 | Paperconfig audit: new `experiments` block, strip time info from `treatment_condition`, add `timepoint_hours`, absorb EnvironmentalCondition | KG |
| 2 | Add `Experiment` node to omics_adapter, `Has_experiment` / `Tests_coculture_with` edges | KG |
| 3 | Change expression edges: `Experiment -[Changes_expression_of]-> Gene`, remove old edge types, compute `rank_by_effect` post-import | KG |
| 4 | Rebuild KG | KG |
| 5 | `list_publications` MCP tool | Explorer |
| 6 | `list_experiments` MCP tool (with edge-aggregated time-point stats) | Explorer |
| 7 | Redefine `query_expression` MCP tool | Explorer |
| 8 | Remove `compare_conditions` MCP tool | Explorer |
| 9 | Update `gene_overview` routing signals for new edge structure | Explorer |
| 10 | Update tests, docs | Explorer |

Steps 1–4 are KG repo. Steps 5–10 are explorer repo. Steps 5–8 can run
in parallel once the KG is rebuilt.

**Deployment:** Full rebuild from scratch (re-import everything). The KG plan
uses a 5-commit sequence (paperconfig_utils refactor → dry-run migration →
apply migration → adapter+schema+post-import → docs). Explorer tools (steps
5–10) are written against the new schema after rebuild. Coordinated cutover:
deploy new KG, then deploy new explorer tools. Old MCP tools will not work
against the new schema (different edge types), so both must ship together.

### Phase 2: Temporal profiling / clustering (follow-up plan)

Deferred to a separate plan. Only Zinser 2009 currently needs it, and it adds
significant scope (new node type, new edge types, new paperconfig type, new
MCP tool). Ship the core DE redesign first, then layer profiling on top.

- ExpressionCluster node, `HAS_CLUSTER` / `IN_EXPRESSION_CLUSTER` edges
- Paperconfig `DIEL_PROFILING` analysis type
- `query_temporal_profile` MCP tool
- Paperconfigs for Zinser 2009 and other profiling/clustering papers

---

## Open questions

1. **Clustering for DE time courses vs diel profiling:** Some papers cluster
   genes by DE response trajectory across a stress time course (e.g., "early
   responders" vs "late responders"). This is structurally similar to diel
   clustering — genes grouped by temporal pattern — but the underlying data
   is fold-changes, not absolute expression. Should these use the same
   `ExpressionCluster` node? The cluster properties differ:
   - Diel cluster: peak_time, periodicity_score
   - DE trajectory cluster: response_pattern ("early_up", "late_down"),
     maybe peak_response_time

   Options:
   - **Same node, different properties** — `ExpressionCluster` is generic
     enough. Add a `cluster_type` field (`"diel"` vs `"response_trajectory"`).
     Unused properties are null.
   - **Different nodes** — `DielCluster` vs `ResponseCluster`. Cleaner
     typing but more node types.

   Leaning same node with `cluster_type` — few papers have this data, and
   the queries are structurally identical. Deferred to Phase 2.

## Deferred to implementation

- `gene_overview` routing signals for temporal profiling data
- `get_schema` update for new node/edge types
- Migration of existing queries_lib.py builders and constants

## Resolved decisions

- **Node label: `Experiment`** (not `Analysis`). Groups time-point analyses
  into the researcher's mental model of an experiment. Individual time-point
  comparisons live on edges, not nodes.

- **Multi-omics = separate Experiments.** RNA-seq and proteomics for the same
  biological setup are two Experiment nodes. Omics type is fundamental to the
  method — mixing transcript and protein fold-changes is misleading.
  `list_experiments` shows them side-by-side for comparison.

- **Time-point normalization:** Both `hours` (numeric, normalized to hours)
  and `order` (ordinal position) on expression edges and in the Experiment
  `time_points` structure. Original string kept as `label`. Paperconfig
  `timepoint_hours` field for explicit numeric value.

- **Separate `query_temporal_profile` tool** (not a mode of
  `query_expression`). Different return schema (peak_time/cluster vs
  log2fc/padj), different questions ("when does it peak?" vs "what changed?").
  Deferred to Phase 2.

- **`treatment_type` on Experiment, `condition_type` in MCP tools.** KG
  stores `treatment_type` (matching paperconfig). MCP tools expose it as
  `condition_type` — more intuitive for the LLM. `"coculture"` is a
  first-class value alongside `"nitrogen_stress"`, `"light_stress"`, etc.
  EnvironmentalCondition nodes are absorbed into Experiment (no separate
  node type).

- **Coculture partner as structured field:** Yes. `coculture_partner` on the
  Experiment node (from paperconfig `treatment_organism`). Enables "coculture
  with Alteromonas" queries without free-text matching.

- **Keyword search on experiments:** Yes. `keyword` parameter on
  `list_experiments` does CONTAINS across name/treatment/control/context.
  Catches experimental detail queries (light regime, medium, temperature)
  that don't warrant dedicated structured filters.

- **Edge label: `Changes_expression_of`** (Neo4j: `Changes_expression_of`).
  Unifies `Condition_changes_expression_of` + `Coculture_changes_expression_of`.
  Reads naturally: "Experiment changes expression of Gene."

- **`rank_by_effect` on expression edges.** Computed post-import: rank each
  gene by |log2FC| within experiment+timepoint. Returned by `query_expression`
  so the LLM knows relative effect size without needing the full dataset.

- **Per-time-point stats computed at query time**, not stored on Experiment
  node. Neo4j can't store nested objects as properties, and these stats are
  derivable from edges. `list_experiments` MCP tool aggregates from
  `Changes_expression_of` edges grouped by `time_point_order`.

- **Experiment node ID: explicit `experiment_group_id`** from paperconfig,
  not derived from grouping rule. Prevents ID instability when treatment text
  or context strings are cleaned up.

- **`query_expression` requires `experiment_id` or `gene_ids`** (at least
  one). Broad filter-only queries would return too many rows.

- **`limit` is per-gene for time courses**, not per-row. Prevents a time
  course from burning the limit on the first few genes × many time points.

- **Temporal profiling deferred to Phase 2.** Only Zinser 2009 currently
  needs it. Ship core DE redesign first, layer profiling on top.

- **Coordinated cutover deployment.** Full KG rebuild + new explorer tools
  ship together. Old tools won't work against new schema.

- **`significant_only` default depends on query mode.** Experiment-centric
  (has `experiment_id`): defaults True — you want highlights. Gene-centric
  (has `gene_ids`): defaults False — absence of response is informative.

- **No `publication` filter on `query_expression`.** The LLM gets experiment
  IDs from `list_experiments(publication="Biller 2018")` and passes them to
  `query_expression`. Adding publication as a third anchor alongside
  `experiment_id` and `gene_ids` complicates mode logic. Keep
  `query_expression` focused on its two modes.

- **`list_filter_values` updated for new schema.** Queries switch from
  EnvironmentalCondition to Experiment node properties. New filter names:
  - `condition_types` — `DISTINCT e.treatment_type` (includes `"coculture"`)
  - `omics_types` — `DISTINCT e.omics_type` (NEW)
  - `gene_categories` — unchanged (from Gene nodes)
  Organism values not needed here — `list_organisms` already covers that.

- **`organism` filter searches both fields.** On `list_publications` and
  `list_experiments`, the `organism` param matches `organism_strain` OR
  `coculture_partner`. "Show me everything involving HOT1A3" finds
  experiments where HOT1A3 is profiled AND where it's the coculture partner.
  `coculture_partner` param on `list_experiments` is a narrower filter for
  when you specifically want "coculture with X."

- **Clustering: same node with `cluster_type`** for both diel and DE
  trajectory clustering. Deferred to Phase 2.
