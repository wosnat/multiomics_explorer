# Cross-tool conventions

Patterns that hold across most or all 37 tools. If you've read a single
tool's doc, these are the things you'd otherwise have to re-learn each
time you read another.

For node and edge meanings see `docs://guide/concepts`.
For tool-by-tool routing see `docs://guide/start_here`.

---

## Response shape: envelope + results

Every tool that returns a list of entities uses the same shape:

```
{
  "total_matching": <int — pre-pagination match count>,
  "returned": <int — rows in this response>,
  "truncated": <bool>,
  "offset": <int>,
  "by_organism": [...],         ← envelope rollups (vary by tool)
  "by_<dim>": [...],
  "top_<thing>": [...],
  "score_max": <float|None>,    ← when search_text is used
  "score_median": <float|None>,
  "not_found": {...},           ← see "Partial-failure buckets" below
  "results": [ {...}, {...} ],  ← per-row detail
}
```

The **envelope** is the top-level dict minus `results`. Envelope rollups
(`by_*`, `top_*`, `*_count`, `score_*`) are computed over the **full
matched set** — they do not depend on `limit` / `offset`. Use them as
the recon view.

Per-row **results** give detail; pagination via `limit` (default 5 on
most tools) and `offset`.

### `summary=True` mode

**31 of 37 tools accept `summary=True`** — nearly universal across
discovery, drill-down, gene-anchored, ontology, and enrichment surfaces.
With `summary=True` the call returns only the envelope (`results=[]`,
`returned=0`, `truncated=true`). Use this as the **first call** for
any question that doesn't already specify exact IDs — the rollups
characterize the full matched set before you commit to a slice.
Pattern: `summary=True` → narrow filters → drop `summary=True` for detail.

The 6 tools without `summary=`: `kg_schema`, `list_filter_values`,
`resolve_gene`, `list_publications`, `gene_response_profile`,
`run_cypher`. These either return small fixed sets, are themselves
summaries (`gene_response_profile`), or have raw / shape-specific
output (`run_cypher`, `kg_schema`).

### `verbose=True` mode

Adds heavy fields (full taxonomy, structural fingerprints, abstracts,
sequence-level data) that you don't usually need. Always read a tool's
"Verbose-only fields" section before passing `verbose=True` — what you
get back per tool varies.

---

## Filter semantics

### AND vs UNION on list filters

Across tools the convention is consistent — but the exact meaning depends
on what's being filtered:

- **List filters that select rows by ID** (`metabolite_ids=[...]`,
  `experiment_ids=[...]`, `publication_doi=[...]`, `assay_ids=[...]`,
  `analysis_ids=[...]`, `cluster_ids=[...]`, `derived_metric_ids=[...]`,
  `term_ids=[...]`, `group_ids=[...]`, `locus_tags=[...]`,
  `organism_names=[...]`) — **UNION** on the filtered set: a row matches
  if it has ANY of the listed IDs. Combined with other filters via AND.

- **Element-presence filters** (`elements=["N", "P"]`,
  `metabolite_elements=["N"]`) — **AND-of-presence**. Every listed
  element must be present.

- **Categorical-set filters** (`evidence_sources=[...]`,
  `gene_categories=[...]`, `categories=[...]`, `metabolite_pathway_ids=[...]`)
  — **set-membership ANY**: a row passes if its values overlap the
  filter. Treat as UNION.

- **`exclude_*_ids` filters** — **set-difference**, exclude wins on
  overlap with the include filter. Empty list is a no-op (treated as
  None). Currently implemented on metabolite-side filters — see
  `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`.

When in doubt, the tool's parameter description always states the
semantics explicitly.

### Single-organism vs cross-organism

Some tools enforce single-organism scope (`organism="..."` is required,
not a list). Some are cross-organism by design (operate on results
across all organisms). Some accept `organisms=[...]` plural for
cross-organism but multi-org filtering.

Single-organism (raises if you pass a list):

- `differential_expression_by_gene`, `gene_response_profile`,
  `gene_ontology_terms`, `genes_by_ontology`, `gene_derived_metrics`,
  `gene_clusters_by_gene`, `genes_in_cluster`, `pathway_enrichment`,
  `cluster_enrichment`, `genes_by_metabolite`, `metabolites_by_gene`.

Cross-organism (operate over the whole graph, no organism scope):

- `genes_by_numeric_metric`, `genes_by_boolean_metric`,
  `genes_by_categorical_metric`, `metabolites_by_quantifies_assay`,
  `metabolites_by_flags_assay`, `assays_by_metabolite`,
  `differential_expression_by_ortholog`.

Cross-organism with `organism_names=[...]` filter:

- `list_organisms`, `list_metabolites`, `list_publications`,
  `list_experiments`, `list_metabolite_assays`, `list_derived_metrics`,
  `genes_by_function`, `search_homolog_groups`, `genes_by_homolog_group`.

The pattern: anything with a precomputed organism-scoped index
(expression, ontology terms, clusters, DM-by-gene) is single-organism;
anything that summarizes or compares across organisms is cross-organism.

### Discovery → drill-down convention

When a "list" / "search" tool returns rows whose IDs you can use as
filter input on a drill-down tool, the discovery tool's per-row fields
are the **routing signals** for which drill-downs are productive. Empty
or zero-valued routing fields mean no evidence — calling the
drill-down anyway returns no rows.

Examples:
- `list_metabolites.results[].gene_count > 0` → `genes_by_metabolite(metabolite_ids=...)`
- `list_metabolites.results[].pathway_count > 0` → `genes_by_ontology(ontology='kegg', term_ids=[pathway_id])`
- `gene_overview.results[].evidence_sources` includes `metabolism` → `metabolites_by_gene(locus_tags=...)`
- `list_experiments.results[].metabolite_count > 0` → `list_metabolite_assays(experiment_ids=...)`
- `list_metabolite_assays.results[].rankable=True` → `metabolites_by_quantifies_assay(rank_by_metric_max=...)`

---

## Partial-failure buckets: `not_found` vs `not_matched`

Most batch tools surface two kinds of partial failure rather than
raising:

- **`not_found`** — the input ID does not exist in the KG at all.
  Almost always a typo or a stale ID. Structured-by-input-bucket on
  multi-batch tools: e.g. `not_found.metabolite_ids`,
  `not_found.organism_names`, `not_found.publication_dois`,
  `not_found.experiment_ids`, `not_found.locus_tags`. On
  single-batch-input tools (`assays_by_metabolite`) it's a flat list.
- **`not_matched`** — the input ID exists in the KG but has no edge to
  the target after filters. E.g. a Metabolite ID with no
  `Reaction_has_metabolite` edge in the queried organism (in
  `genes_by_metabolite`); a locus_tag in a different organism (in
  single-organism drill-downs); a DM ID whose `value_kind` doesn't
  match the tool (in `gene_derived_metrics`). Diagnostic: the row
  exists, but the question doesn't apply.

Always inspect both. An empty `results` plus a populated `not_found` or
`not_matched` is *not* "no biology" — it's a routing problem.

---

## Tested-absent rows are real biology

In the metabolomics layer (`MetaboliteAssay` edges), the KG stores
**tested-and-not-detected** rows alongside tested-and-detected ones:

- `Assay_quantifies_metabolite` carries `detection_status ∈ {detected, not_detected, ...}`. About 75% of numeric edges are `not_detected`. That's a deliberate biological signal — the metabolite was looked for under that condition and not found, in contrast to "not measured at all".
- `Assay_flags_metabolite` carries `flag_value ∈ {True, False}`. About 62% of boolean rows are `flag_value=False`. Same semantics.

**Tools default to keeping tested-absent rows.** Filter them out only
when you have a specific reason. Envelope rollups
(`by_detection_status`, `by_flag_value`) surface this composition as
the primary headline. See `docs://analysis/metabolites`.

The expression layer (`Changes_expression_of` edges) has the same
question — was this gene tested-and-not-significant, or never
reported? — but the answer depends on the parent experiment's
`table_scope`:

- `table_scope='all_detected_genes'` — the paper reported every
  detected gene including non-significant ones. Tested-absent rows
  are present (`expression_status='not_significant'`); a gene with no
  edge means truly not detected by the assay.
- `table_scope='significant_only'` (or `top_n`) — the paper reported
  only significant genes. Tested-absent collapses with not-detected:
  a gene with no edge could mean either, and you can't tell from the
  KG. Be careful when interpreting absence in these experiments.

Always check the experiment's `table_scope` (surfaced on
`list_experiments` and the per-row context of
`differential_expression_by_gene`) before drawing conclusions from
missing rows. Same gene can carry both shapes simultaneously across
different experiments.

The DerivedMetric layer is **positive-only by storage convention** —
`Derived_metric_flags_gene` only stores edges for `flag=True`, so
`flag=False` returns 0 rows. Tested-absent semantics on the DM side
are not currently representable.

---

## Annotation quality (`[AQ]` footnote)

`Gene.annotation_quality` is a 0..3 numeric encoding of
`Gene.annotation_state` (informative-evidence count). Redefined in the
May 2026 KG release:

- `0` = `no_evidence` (no informative annotation)
- `1` = `catch_all_only` (gene name / product is a catch-all term)
- `2` = `informative_single` (one informative annotation type)
- `3` = `informative_multi` (multiple informative annotation types)

`min_quality=2` is the recommended filter to skip hypothetical proteins.
`min_quality=3` for high-confidence gene sets.

**Drift caveat.** Pre-2026-05 the field encoded product-name quality.
Existing notebooks or session memory using `min_quality` may now select
a different gene set. The redefinition is silent at the API boundary —
you will not get a deprecation warning. Affected tools:
`genes_by_function`, `gene_details`, `gene_overview`, plus any tool
filtering on `annotation_quality`.

---

## Informative-only filtering on enrichment + ontology (`[ENR]` footnote)

As of the 2026-05 KG release, both `pathway_enrichment` and
`cluster_enrichment` default to `informative_only=True`. Uninformative
ontology terms (`is_uninformative='true'` in the KG) are excluded from
the Fisher tests by default. This filters out catch-all terms like
KEGG `map00001` "metabolic pathways" (~40% of the genome) and GO root
`go:0008150` "biological_process" (~all annotated genes), which would
otherwise dominate any enrichment ranking.

The same default applies to `ontology_landscape`, `search_ontology`,
`genes_by_ontology`, and `gene_ontology_terms`. Pass
`informative_only=False` to opt out (e.g. to confirm that an
uninformative term is the top hit, or to lock in pre-2026-05 row
counts). Per-row `is_informative` is surfaced regardless of the
parameter, so you can post-filter.

**Reproducibility caveat.** BH-adjusted p-values depend on the term
set tested in each cluster. With the default flipped, prior runs that
included uninformative terms have different `p_adjust` values from
new runs even on identical inputs. The raw `pvalue` is unaffected.
For locked baselines, pass `informative_only=False` and post-filter
on `is_informative`. Full methodology in `docs://analysis/enrichment`.

---

## DM family gating

The DerivedMetric drill-down tools (`genes_by_numeric_metric`,
`genes_by_boolean_metric`, `genes_by_categorical_metric`) accept some
filters that only apply to specific DM subsets. The contract is
consistent across all three:

- **Always-available filters** (raw value, flag, category) — work on every selected DM.
- **Rankable-gated filters** (`metric_bucket`, `metric_percentile_*`, `rank_by_metric_max`) — only meaningful on DMs with `rankable=True`.
  - Mixed-rankability input → soft-exclude non-rankable DMs, surface them in the envelope's `excluded_derived_metrics` + `warnings`.
  - All-non-rankable input + a rankable-gated filter → raises.
- **`has_p_value`-gated filters** — analogous; raises today on missing p-values.

Inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories`
on `list_derived_metrics` results before drill-down. The same shape
applies to `metabolites_by_quantifies_assay` (`rankable` lives on
`MetaboliteAssay`) — rankable-gated filters there raise iff every
selected assay is non-rankable, soft-exclude on mixed input.

---

## Transport-confidence discriminator (chemistry)

Substrates in TCDB are curated at the **leaf** level
(`tc_specificity`), and the rollup unions those substrates **up** the
family hierarchy: every ancestor family is annotated with the union of
substrates curated for any of its descendant leaves. The design rationale
is biological: transporter substrate specificity is uncertain, so genes
annotated to broad TCDB families (common in homology-based annotation)
can still surface the candidate substrates curated at any descendant
leaf. The `transport_confidence` field on transport rows discriminates
the two cases:

- **`substrate_confirmed`** — the gene is annotated to the leaf
  (`tc_specificity`) family that is *itself* curated for this
  metabolite. Direct evidence.
- **`family_inferred`** — the gene is annotated to a non-leaf ancestor
  family. The metabolite is curated on *some* descendant leaf, but
  we don't know which specific subfamily applies to this gene. Lower
  precision, broader-screen evidence.

`family_inferred` dominates by volume (per-gene median ≈ 6 metabolites
of substrate evidence, p90 ≈ 90, max = 551 via the ABC superfamily).
`metabolites_by_gene` and `genes_by_metabolite` emit an automatic
warning when `family_inferred` overwhelms `substrate_confirmed` on
the result set, and `metabolites_by_gene` sorts globally by precision
tier so a single ABC-only gene cannot consume the `limit`.

Filter with `transport_confidence=['substrate_confirmed']` to suppress
the rollup-tier rows when precision matters. See `docs://analysis/metabolites`
for the full discriminator semantics.

---

## Direction-agnosticism in chemistry

KEGG reactions are stored in the KG **without substrate-vs-product
direction** — KEGG equation order is unreliable upstream, so we do not
encode it. Joins through `Reaction_has_metabolite` and
`Tcdb_family_transports_metabolite` will return both produced and
consumed metabolites identically. Reversibility is similarly absent
on `Reaction` nodes (KEGG lacks an `is_reversible` flag).

To distinguish directionality, layer:

- **DE direction** (`differential_expression_by_gene` `direction='up'`
  vs `'down'`) — transcriptional response under treatment.
- **Functional annotation** (`gene_overview` Pfam/KO labels —
  `*-synthase` vs `*-permease`, `*-dehydrogenase` vs
  `*-hydratase`) — text-level disambiguation.

Always restate the caveat when you answer with metabolite chemistry —
"this gene catalyses a reaction involving X" rather than "this gene
produces X". This is the permanent convention; see
`docs://analysis/metabolites`.

---

## Pagination

`limit` and `offset` control row pagination on every tool that
returns a `results` list. The defaults differ by surface:

- **MCP:** `limit=5` on most tools (sometimes higher). Pages must be
  walked with explicit `offset=` calls.
- **Package:** `limit=None` — returns every matching row by default.
  Set `limit=` / `offset=` explicitly if you want MCP-style paging
  (e.g. for a UI).

`total_matching` is always the **pre-pagination** count of all rows
matching the filters; `returned` is the size of the current page;
`truncated=True` means more rows are available beyond `offset +
returned`.

**Envelope rollups are computed over the full matched set, not the
current page.** `by_organism`, `by_metric`, `top_*`, `score_max`,
`mass_stats`, etc. are identical across pages of the same query —
they describe `total_matching` rows, not `returned` rows. This is
deliberate: the envelope is the recon view, designed to characterize
the slice before you commit to paginating its details.

For analysis workflows that need all rows (enrichment background
sets, batch DataFrame extraction), use the **package import**: every
tool md has a "Package import equivalent" section. MCP is for
reasoning and interactive exploration; the package is for bulk
extraction.

---

## Background semantics for enrichment

`pathway_enrichment` and `cluster_enrichment` accept three background
modes:

- **`table_scope`** (default for `pathway_enrichment`) — per-cluster
  background = the gene universe quantified in that experiment. Use
  this whenever the gene set came from a DE table.
- **`cluster_union`** (default for `cluster_enrichment`) — per-cluster
  background = all genes in the parent ClusteringAnalysis (the
  clustering universe).
- **`organism`** — full organism gene set. Use for whole-genome
  analyses that aren't tied to any quantification table.
- **Custom list** — pass a `list[str]` of locus_tags as `background=`
  for hand-defined backgrounds.

The choice of background matters more than the choice of ontology.
`docs://analysis/enrichment` §9 has the full discussion.

---

## Hierarchy `level` convention (ontology tools)

For all 10 supported ontologies, `level: int` follows the same convention:

- **`level=0`** = root (broadest term).
- Higher integers = more specific.
- Tree-shaped ontologies (Cyanorak, TIGR, COG, EC) have exact level
  semantics.
- DAG-shaped ontologies (GO, sometimes KEGG) use min-path-from-root
  with a sparse `level_is_best_effort='true'` flag on affected terms.

`ontology_landscape` ranks (ontology × level) combinations by
`relevance_rank` baking in genome coverage and median term size; use it
to pick a defensible level before enrichment.

---

## BRITE: always scope with `tree=`

BRITE is a meta-ontology of multiple independent classification trees
(enzymes, transporters, protein families, brite-mapping, etc). Running
all-BRITE enrichment without `tree=` is dominated by the largest tree
(enzymes, ~1776 terms), drowning smaller-tree signal. Every BRITE-aware
tool accepts `tree=` — discover valid tree names via
`list_filter_values(filter_type='brite_tree')`.

Tools that accept `tree=`: `genes_by_ontology`, `gene_ontology_terms`,
`search_ontology`, `ontology_landscape`, `pathway_enrichment`,
`cluster_enrichment`.

---

## Organism naming

`OrganismTaxon.preferred_name` is the canonical identifier (e.g.
`"Prochlorococcus MED4"`, `"Alteromonas macleodii MIT1002"`). The
matching rule depends on the parameter:

- **`organism_names=[...]`** (plural, list) — exact match,
  case-insensitive on `preferred_name`. Unknown names surface in
  `not_found.organism_names`.
- **`organism="..."`** (singular, scalar) — exact match,
  case-insensitive on `preferred_name`. Some tools allow shorthand
  (`"MED4"`), but the safe convention is the full preferred_name.

Use `list_organisms()` to enumerate. Substring matching on partial
names will silently miss — `"MED4"` won't match
`"Prochlorococcus MED4"` on tools that require exact `preferred_name`.

`organism=` filters the **profiled organism only** on tools where it
applies (`list_experiments`, `differential_expression_by_gene`). For
coculture-partner-side filtering use `coculture_partner=` — the two
fields are distinct.

---

## Score fields (Lucene search)

Tools with `search_text=` parameters use a Neo4j fulltext index and
return Lucene relevance scores. When `search_text` is set:

- Each row carries a `score: float` field.
- The envelope carries `score_max: float | None` and
  `score_median: float | None` (only when `search_text` is non-null).
- Results are sorted by score desc by default.
- Lucene syntax is supported (boolean operators, phrase matching,
  fuzzy with `~`, field-boosting). E.g.
  `search_text="phosphate AND (transporter OR permease)"`.

Tools with Lucene search: `genes_by_function`, `search_ontology`,
`search_homolog_groups`, `list_metabolites`, `list_metabolite_assays`,
`list_derived_metrics`, `list_clustering_analyses`, `list_experiments`,
`list_publications`.

---

## When to use the package import vs MCP

Every tool md has a "Package import equivalent" section showing the
matching Python function. Quick contract:

- **MCP** — reasoning, interactive exploration, single-question slices.
  Paginates by `limit` / `offset`.
- **Package import** — bulk extraction, multi-step pipelines, DataFrame
  workflows. `limit=None` by default — returns every matching row.

For the full Python-API surface (import topology, three return shapes
including `EnrichmentResult` and DataFrame-returning analysis utilities,
connection management, DataFrame conversion, worked recipes), read
`docs://guide/python_api`.
