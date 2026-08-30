# Cross-tool conventions

Patterns that hold across most or all 42 tools. If you've read a single
tool's doc, these are the things you'd otherwise have to re-learn each
time you read another.

For node and edge meanings see `docs://guide/concepts`.
For tool-by-tool routing (families, decision tree, discover → drill
table) see `docs://guide/start_here`. For the Python package (pagination
defaults, return shapes, DataFrames) see `docs://guide/python_api`.

> **Numbers in example responses are illustrative snapshots.** The `response:`
> blocks in per-tool docs (counts, `total_matching`, rollup values, example IDs)
> were captured from one KG build and are not kept in sync with the live graph —
> they show response *shape*, not current values. For real counts, run the call.

**Contents**

1. [Response shape: envelope + results](#response-shape-envelope--results) — `summary` / `verbose`
2. [Filter semantics](#filter-semantics) — AND vs UNION, `exclude_*_ids`, organism scope
3. [Partial-failure buckets](#partial-failure-buckets-not_found-vs-not_matched) — the three `not_found` shapes
4. [Empty per-gene results](#empty-per-gene-results-no-hit-vs-out-of-scope)
5. [Tested-absent rows](#tested-absent-rows-are-real-biology) — metabolomics, `table_scope`, two-state strings
6. [Annotation quality `[AQ]`](#annotation-quality-aq-footnote)
7. [Informative-only filtering `[ENR]`](#informative-only-filtering-on-enrichment--ontology-enr-footnote)
8. [DM family gating](#dm-family-gating)
9. [Chemistry](#transport-trust-ladder-chemistry) — transport trust ladder, direction, metabolite ID forms
10. [Pagination](#pagination) — lockstep paging, browse vs search
11. [Annotation-trust surface](#annotation-trust-surface-ontology-tools) — `level`, BRITE `tree=`
12. [Organism naming](#organism-naming) · [Score fields](#score-fields-lucene-search)

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
  "not_found": [...] | {...},   ← shape varies by tool — see "Partial-failure buckets"
  "not_matched": [...],
  "warnings": [...],            ← soft diagnostics (collisions, gates, truncated browses)
  "resolved_aliases": {...},    ← chemistry / metabolomics tools only
  "excluded_derived_metrics" / "excluded_assays": [...],  ← DM / assay drill-downs only
  "skipped_ontologies": [...],  ← multi-ontology term tools only
  "results": [ {...}, {...} ],  ← per-row detail
}
```

The **envelope** is the top-level dict minus `results`. Envelope rollups
(`by_*`, `top_*`, `*_count`, `score_*`) are computed over the **full
matched set** — they do not depend on `limit` / `offset`. Use them as
the recon view.

Per-row **results** give detail; pagination via `limit` (default 5 on
most tools) and `offset`.

### Breakdown caps on detail calls

Envelope rollup lists (`by_*`, `top_*`) that can grow past a handful of
entries are capped to the **first 10** on a detail call (`summary=False`,
the default) — the list is sorted desc by its ranking count first, so the
10 that survive are the 10 that matter. When a cap actually trims a list,
a sparse sibling key `<key>_truncated` appears next to it: `<key>_truncated`
is `true` when capped; otherwise absent in Python / `null` over MCP (the
Pydantic response model declares every `Optional` field, so FastMCP's wire
format fills the unset key with `null` — it is never simply missing on the
wire the way it is in the Python dict). The list was already ≤10 entries
when the key is absent/null, so goldens and examples only change where a
list genuinely exceeded the cap.
`summary=True` always returns the **full, uncapped** list — read it first
when you need the whole ranking (e.g. every organism's chemistry capability,
not just the top 10). Affected: `list_experiments` / `list_organisms`
(`by_organism`, `by_metric_type`, `by_publication`, `by_treatment_type`,
`by_background_factors`, `top_annotation_capability`,
`top_metabolic_capability`, …), `genes_by_function` (`by_organism`),
`genes_by_metabolite` / `metabolites_by_gene` (`top_genes`, `top_reactions`,
`top_tcdb_families`, `top_metabolite_pathways`, `by_element`),
`differential_expression_by_gene` / `differential_expression_by_ortholog`
(`experiments`), `pathway_enrichment` (`by_experiment`), and `resolve_gene`
/ `list_publications` (`by_organism`; `by_organism` and `by_metric_type`
respectively) — `summary=True` restores the full list (on `resolve_gene`
the `by_organism` counts then sum exactly to `total_matching`; on
`list_publications` a multi-organism paper counts once per organism).
`pathway_enrichment`'s `top_pathways_by_padj` is a genuine top-10 in both
modes (not capped-with-a-flag): it carries no `_truncated` companion key.

### `summary=True` mode

**36 of 42 tools accept `summary=True`** — nearly universal across
discovery, drill-down, gene-anchored, ontology, and enrichment surfaces.
With `summary=True` the call returns only the envelope (`results=[]`,
`returned=0`; `truncated` is `true` whenever rows were withheld and
`false` when nothing matched). Use this as the **first call** for
any question that doesn't already specify exact IDs — the rollups
characterize the full matched set before you commit to a slice.
Pattern: `summary=True` → narrow filters → drop `summary=True` for detail.
Exception to "summary is the cheap call": on `metabolites_by_gene` the
envelope (`by_gene`, `top_metabolites`, …) is computed over the whole
locus-tag batch, so `summary=True` on 50+ genes costs as much as a detail
call — use it because the envelope is the artifact, not to save time.

The 6 tools without `summary=`: `kg_schema`, `kg_release_info`, `ontology_term_details`,
`list_filter_values`, `gene_response_profile`, `run_cypher`. These either return small fixed
sets, are themselves summaries (`gene_response_profile`), take a bounded
batch (`ontology_term_details`), or have raw / shape-specific output
(`run_cypher`, `kg_schema`).

### `warnings`: advisory diagnostics

`warnings` (`list[str]`, always present, `[]` when clean) surfaces things
worth a second look — a closed-vocabulary filter value that matched no
`ControlledVocabulary` entry (`treatment_type`, `background_factors`,
`compartment`, `table_scope`, `growth_phases`, `omics_type`, `category` /
`gene_categories`, `cluster_type`), an `organism` word that resolved to no
`OrganismTaxon`, a rankable/has_p_value gate exclusion, an ID collision, a
`not_found` locus_tag that differs only by case from a real `Gene.locus_tag`
(`gene_overview`, `gene_details`, `gene_homologs`, `gene_aa_sequence`,
`gene_neighbors`, `gene_ontology_terms`, `differential_expression_by_gene`,
`gene_response_profile`, `gene_derived_metrics`, `gene_clusters_by_gene`,
`metabolites_by_gene`), and similar. A warning is **advisory only — it never
changes which rows come back**; the call still runs against whatever the
filters actually matched (often an empty result), it just tells you *why*.
Each warning names the tool to call for the valid set — usually
`list_filter_values(filter_type=...)` for a vocabulary typo,
`list_organisms()` for an unmatched organism.

### `verbose=True` mode

Adds heavy fields (full taxonomy, structural fingerprints, abstracts,
sequence-level data, per-edge trust detail) that you don't usually need.
Always read a tool's "Verbose-only fields" section before passing
`verbose=True` — what you get back per tool varies.

---

## Filter semantics

### AND vs UNION on list filters

Across tools the convention is consistent — but the exact meaning depends
on what's being filtered:

- **List filters that select rows by ID** (`metabolite_ids=[...]`,
  `experiment_ids=[...]`, `publication_doi=[...]`,
  `publication_dois=[...]`, `assay_ids=[...]`,
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

- **`exclude_metabolite_ids`** — **set-difference**, exclude wins on
  overlap with `metabolite_ids`. Empty list is a no-op (treated as
  None). Present on all seven chemistry / metabolomics tools
  (`list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`,
  `list_metabolite_assays`, `metabolites_by_quantifies_assay`,
  `metabolites_by_flags_assay`, `assays_by_metabolite`); its typical use
  is stripping currency cofactors (ATP, NADH, water) from a chemistry
  answer. Accepts the same alias forms as `metabolite_ids` — see
  "Metabolite ID forms" below.

- **Controlled-vocabulary filters** (`treatment_type`, `background_factors`,
  `compartment`, `growth_phases`, `omics_type`, `cluster_type`, the trust
  vocabularies) match exact values. An unknown value returns 0 rows, not
  an error — read the live set with `list_filter_values(filter_type=...)`
  before guessing a spelling.

When in doubt, the tool's parameter description always states the
semantics explicitly.

### Single-organism vs cross-organism

Three shapes of organism scope exist. All scalar `organism=` values go
through the same resolver (see "Organism naming" below).

**Required scalar `organism=`** — the query needs one gene universe
(a TERM2GENE mapping, a background, a single-organism chemistry join).
Omitting it raises; passing a list raises:

- `genes_by_ontology`, `gene_ontology_terms`, `ontology_landscape`,
  `pathway_enrichment`, `cluster_enrichment`, `genes_by_metabolite`,
  `metabolites_by_gene`.

**Optional scalar `organism=`, single organism enforced** — the tool
infers the organism from the input IDs (locus tags / experiment IDs /
cluster IDs) when you omit it, and raises when those IDs span more than
one organism. Pass `organism=` to disambiguate or to narrow:

- `differential_expression_by_gene`, `gene_response_profile`,
  `gene_derived_metrics`, `gene_clusters_by_gene`, `genes_in_cluster`.

**Cross-organism** — rows from any organism; `organism=` (scalar) or
`organisms=[...]` (list) is an optional narrowing filter:

- Scalar `organism=`: `genes_by_function`, `resolve_gene`,
  `list_experiments`, `list_publications`, `list_clustering_analyses`,
  `list_derived_metrics`, `list_metabolite_assays`, `search_ontology`,
  `ontology_term_details`, `genes_by_{numeric,boolean,categorical}_metric`,
  `metabolites_by_{quantifies,flags}_assay`, `assays_by_metabolite`.
- List `organisms=[...]`: `genes_by_homolog_group`,
  `differential_expression_by_ortholog`.
- List `organism_names=[...]`: **only** `list_organisms` and
  `list_metabolites`. Unknown names land in `not_found` (flat list on
  `list_organisms`, `not_found.organism_names` on `list_metabolites`).
- No organism parameter at all: `gene_overview`, `gene_details`,
  `gene_homologs`, `gene_aa_sequence`, `gene_neighbors`,
  `search_homolog_groups`, `discussed_by_publication` (DOIs are
  organism-agnostic; gene rows still carry per-row `organism`).

The pattern: anything that needs a precomputed organism-scoped index
(ontology terms, backgrounds, chemistry joins) is single-organism;
anything that summarizes or compares across organisms is cross-organism.
`organism=` filters the **profiled organism only** on `list_experiments`
and `differential_expression_by_gene`; for coculture-partner-side
filtering use `coculture_partner=`.

Per-row routing signals on discovery tools (`expression_edge_count`,
`catalyst_gene_count`, `evidence_sources`, `rankable`, ...) tell you
which drill-downs are productive — the discover → drill table in
`docs://guide/start_here` lists the pairs.

---

## Partial-failure buckets: `not_found` vs `not_matched`

Most batch tools surface two kinds of partial failure rather than
raising:

- **`not_found`** — the input ID does not exist in the KG at all.
  Almost always a typo or a stale ID.
- **`not_matched`** — the input ID exists in the KG but has no edge to
  the target after filters. E.g. a Metabolite ID with no
  `Reaction_has_metabolite` edge in the queried organism (in
  `genes_by_metabolite`); a locus_tag in a different organism (in
  single-organism drill-downs); a DM ID whose `value_kind` doesn't
  match the tool (in `gene_derived_metrics`); a DOI that exists but
  names no genes or pathways in prose (in `discussed_by_publication`).
  Diagnostic: the row exists, but the question doesn't apply.

The **key shape** depends on how many ID batches the tool accepts:

| Shape | Used by | Example |
|---|---|---|
| Flat `not_found: list[str]` (+ flat `not_matched` where the tool distinguishes it) — one input batch | `gene_overview`, `gene_details`, `gene_homologs`, `gene_aa_sequence`, `gene_neighbors`, `gene_clusters_by_gene`, `gene_derived_metrics`, `gene_ontology_terms`, `genes_by_ontology`, `ontology_term_details`, `ontology_landscape`, `pathway_enrichment`, `cluster_enrichment`, `list_organisms`, `list_publications`, `list_experiments`, `gene_response_profile`, `assays_by_metabolite`, `discussed_by_publication` | `gene_overview(locus_tags=["PMM0001","NOPE"])` → `not_found: ["NOPE"]` |
| Dict keyed by input bucket — `not_found.metabolite_ids`, `.assay_ids`, `.experiment_ids`, `.publication_doi`, `.organism_names`, `.pathway_ids`, ... (only the buckets that tool accepts) | the six multi-batch chemistry / metabolomics tools: `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`, `list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay` | `list_metabolite_assays(assay_ids=["x"], experiment_ids=["y"])` → `not_found: {assay_ids: ["x"], experiment_ids: ["y"], ...}` |
| Suffixed flat lists — `not_found_<bucket>` / `not_matched_<bucket>` per input batch | `genes_by_homolog_group` (`_groups`, `_organisms`), `differential_expression_by_ortholog` (`_groups`, `_organisms`, `_experiments`), `differential_expression_by_gene` (flat `not_found` for genes + `_experiments`), `genes_in_cluster` (`_clusters`, `not_matched_organism`), `genes_by_{numeric,boolean,categorical}_metric` (`_ids`, `_metric_types`, `not_matched_organism`) | `genes_by_homolog_group(group_ids=["cyanorak:CK_1"], organisms=["MED4","Mars"])` → `not_found_organisms: ["Mars"]` |
| tool-specific diagnostic buckets — `wrong_ontology`, `wrong_level`, `filtered_out` (`genes_by_ontology`); `no_expression`, `filtered_out`, `not_found_experiments` (DE tools); `no_groups` (`gene_homologs`) | `genes_by_ontology`, `differential_expression_by_gene`, `gene_response_profile`, `gene_homologs` | `{"filtered_out": ["PMM1171"], "not_found_experiments": []}` |

Tools that take no ID batch (`genes_by_function`, `search_ontology`,
`search_homolog_groups`, `list_clustering_analyses`, `list_derived_metrics`,
`resolve_gene`) have no `not_found` at all — an empty `results` there is
simply no match. `gene_homologs` and `search_ontology` also name their
empty states per row (`no_groups`, `skipped_ontologies`) — read the tool
page.

Always inspect both buckets. An empty `results` plus a populated `not_found` or
`not_matched` is *not* "no biology" — it's a routing problem.

---

## Empty per-gene results: "no hit" vs "out of scope"

A per-gene tool returning nothing for a gene (`gene_homologs`
`no_groups`, `gene_ontology_terms` zero rows, `gene_clusters_by_gene` /
`gene_derived_metrics` `not_matched`) does **not** by itself mean the
biology is absent. Three cases collapse into "empty":

- the gene exists and the upstream source ran but found nothing
  ("no hit"),
- the gene exists but the source never applied to it ("out of scope"),
- the gene isn't in the KG (`not_found` — already distinguished above).

Don't read an empty result as a biological negative. The actionable
signal is already on `gene_overview`: **`annotation_state`**
(`no_evidence` / `catch_all_only` / `informative_single` /
`informative_multi`) tells you whether the gene has informative
evidence at all. For the rarer "ran-but-empty vs never-ran"
distinction, the Gene node also carries **`contributing_sources`**
(`gene_details`) — the pipelines that contributed at least one field:
`ncbi`, `uniprot`, `cyanorak`, `eggnog`, `interproscan`, `psortb`,
`signalp`, `tcdb_diamond`, `merops_diamond`.

**Cross-organism caveat:** `cyanorak`-derived annotations (Cyanorak
roles, curated products, many ortholog groups) apply to
**Prochlorococcus / Synechococcus only**. Heterotroph genes
(Alteromonas, Pseudomonas, Marinobacter, Meiothermus, …) lack them
**by design** — out-of-scope, not a data gap. Don't infer that a
heterotroph clade is "poorly annotated" from missing Cyanorak /
ortholog coverage.

---

## Tested-absent rows are real biology

In the metabolomics layer (`MetaboliteAssay` edges), the KG stores
**tested-and-not-detected** rows alongside tested-and-detected ones:

- `Assay_quantifies_metabolite` carries `detection_status ∈ {detected, not_detected, ...}`. About 70% of numeric edges are `not_detected`. That's a deliberate biological signal — the metabolite was looked for under that condition and not found, in contrast to "not measured at all".
- `Assay_flags_metabolite` carries `flag_value` (`detected` / `not_detected` in the KG, surfaced as `True` / `False`). About 69% of boolean edges are `flag_value=False`. Same semantics.

**Tools default to keeping tested-absent rows.** Filter them out only
when you have a specific reason. Envelope rollups
(`by_detection_status`, `by_flag_value`) surface this composition as
the primary headline. See `docs://analysis/metabolites`.

### Expression: `table_scope` decides what absence means

The expression layer (`Changes_expression_of` edges) has the same
question — was this gene tested-and-not-significant, or never
reported? — but the answer depends on the parent experiment's
`table_scope`:

- `table_scope='all_detected_genes'` — the paper reported every
  detected gene including non-significant ones. Tested-absent rows
  are present (`expression_status='not_significant'`); a gene with no
  edge means truly not detected by the assay.
- Any other scope (`significant_only`, `significant_any_timepoint`,
  `filtered_subset`, `top_n`) — the paper reported only a subset.
  Tested-absent collapses with not-detected: a gene with no edge could
  mean either, and you can't tell from the KG. Be careful when
  interpreting absence in these experiments.

Always check the experiment's `table_scope` (surfaced on
`list_experiments` and the per-row context of
`differential_expression_by_gene`) before drawing conclusions from
missing rows. The same gene can carry both shapes simultaneously across
different experiments.

`table_scope` is **sparse**: an experiment with no DE table at all — a
characterization study (mRNA decay, promoter mapping) or a
metabolomics-only experiment — carries no `table_scope` property, never
an empty string. `list_experiments.by_table_scope` has no `""` bucket
and `table_scope=[...]` filters never match those experiments.

### Dense experiment metadata

- **`treatment_type` is dense and never empty.** It is present on every
  `Experiment`, `ClusteringAnalysis`, `DerivedMetric` and `MetaboliteAssay`,
  and a non-empty list is the marker of a real experiment. A study with no
  perturbation names *what was measured* instead: `rna_decay` (mRNA
  half-life survey), `tss_mapping` (TSS / promoter survey),
  `genomic_analysis` (sequence-predicted genomic islands). Filter on those
  values to isolate characterization studies — never test for `[]`.
  `background_factors` is likewise dense. On `Experiment` it is never empty
  (every experiment has a held-constant context); it is `[]` only on
  sequence-only clustering analyses, which have no experimental context.
- **`growth_phases` is an open vocabulary.** New papers add new labels;
  enumerate live via `list_filter_values(filter_type='growth_phase')`
  rather than assuming a fixed set. `treatment_type`, `cluster_type` and
  the trust vocabularies are closed and readable via `list_filter_values`.

### Two-state strings

Boolean-like properties are stored as **two-state strings** in the KG
(`Experiment.is_time_course`: `time_course` / `single_time_point`;
`DerivedMetric.rankable`: `rankable` / `not_rankable`;
`DerivedMetric.has_p_value`: `p_value` / `no_p_value`;
`Derived_metric_flags_gene.value`: `flagged` / `not_flagged`;
`Assay_flags_metabolite.flag_value`: `detected` / `not_detected`). Tool
parameters and most output columns stay `bool`;
`differential_expression_by_ortholog.experiments[*].is_time_course` and the
`genes_by_boolean_metric.by_value` rollup surface the KG literal. On the DM
side, tested-absent (`not_flagged`) edges exist on 11 of 27 boolean DMs —
the rest are positive-only, so `genes_by_boolean_metric(flag=False)` is
DM-dependent (read `by_metric[*].false_count`). `Assay_flags_metabolite`
always stores both states.

---

## Annotation quality (`[AQ]` footnote)

`Gene.annotation_quality` is a 0..3 numeric encoding of
`Gene.annotation_state` (informative-evidence count):

- `0` = `no_evidence` (no informative annotation)
- `1` = `catch_all_only` (gene name / product is a catch-all term)
- `2` = `informative_single` (one informative annotation type)
- `3` = `informative_multi` (multiple informative annotation types)

`min_quality=2` is the recommended filter to skip hypothetical proteins.
`min_quality=3` for high-confidence gene sets.

**Drift caveat.** Earlier KG releases encoded product-name quality in the
same field. Existing notebooks or session memory using `min_quality` may
now select a different gene set. The redefinition is silent at the API
boundary — you will not get a deprecation warning. Affected tools:
`genes_by_function`, `gene_details`, `gene_overview`, plus any tool
filtering on `annotation_quality`.

---

## Informative-only filtering on enrichment + ontology (`[ENR]` footnote)

`pathway_enrichment`, `cluster_enrichment` and `ontology_landscape`
default to `informative_only=True`. Uninformative ontology terms
(`is_uninformative='true'` in the KG) are excluded from the Fisher tests
and the landscape ranking by default; per-row `is_informative` is
surfaced regardless, so you can post-filter.

`search_ontology`, `genes_by_ontology` and `gene_ontology_terms` default
to `informative_only=False` — they show every term, because a lookup
should not hide what a gene is annotated to. Pass `informative_only=True`
to those when you want the enrichment-eligible subset only.

**What is flagged.** The flag is set per ontology by the KG build. GO
roots (`go:0008150` "biological_process" and its siblings) are flagged.
In KEGG, KO-level catch-alls ("uncharacterized protein") and the
global / overview maps (`kegg.pathway:ko01100` "Metabolic pathways",
`ko01110`, `ko01120`, the `ko012xx` block — 11 of the 13 parentless
pathway nodes) are flagged; `ko01310` Nitrogen cycle and `ko01320`
Sulfur cycle are kept informative, and category / subcategory nodes are
never flagged (gate those with `level`). KEGG pathway IDs are
always the `kegg.pathway:ko…` form — there are no `map…` IDs in the KG.
Which terms an ontology flags and why: `docs://ontologies/{key}`
"Informativeness rule".

**Reproducibility caveat.** BH-adjusted p-values depend on the term
set tested in each cluster. Runs that include uninformative terms have
different `p_adjust` values from runs that exclude them, even on
identical inputs. The raw `pvalue` is unaffected. For locked baselines,
pass `informative_only=False` and post-filter on `is_informative`. Full
methodology in `docs://analysis/enrichment`.

---

## DM family gating

The DerivedMetric drill-down tools (`genes_by_numeric_metric`,
`genes_by_boolean_metric`, `genes_by_categorical_metric`) accept some
filters that only apply to specific DM subsets. The contract is
consistent across all three:

- **Always-available filters** (raw value, flag, category) — work on every selected DM.
- **Rankable-gated filters** (`bucket`, `min_percentile` / `max_percentile`, `max_rank` — they populate the row fields `metric_bucket`, `metric_percentile`, `rank_by_metric`; the assay twins spell the same filters `metric_bucket`, `metric_percentile_min` / `_max`, `rank_by_metric_max`) — only meaningful on DMs with `rankable=True`.
  - Mixed-rankability input → soft-exclude non-rankable DMs, surface them in the envelope's `excluded_derived_metrics` + `warnings`.
  - All-non-rankable input + a rankable-gated filter → raises.
- **`has_p_value`-gated filters** (`significant_only`, `max_adjusted_p_value`) — analogous; raise when no selected DM carries p-values.

Inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories`
on `list_derived_metrics` results before drill-down. The same shape
applies to `metabolites_by_quantifies_assay` (`rankable` lives on
`MetaboliteAssay`, exclusions land in `excluded_assays`) — rankable-gated
filters there raise iff every selected assay is non-rankable,
soft-exclude on mixed input.

---

## Transport trust ladder (chemistry)

TCDB substrates are attached to transporter family nodes and inherited
down the family hierarchy, so a gene annotated to a broad family (common
in homology-based annotation) still surfaces candidate substrates. Read
transport evidence as a three-level ladder, top down:

1. **`tcdb_evidence_score`** (transport row) / **`tcdb_evidence_score_max`**
   (gene; `gene_overview`, `top_genes`, `by_gene`) — how corroborated the
   gene × family call is, on `[0, 1]`. Rank by it; never filter by it. `0`
   is an uncorroborated hit, not an absent call — absent is
   `tcdb_evidence_score_max = None` (no TCDB call on the gene at all). The
   `'tcdb' ∈ annotation_types` gate on `gene_overview` is the binary
   version of the same evidence; the score is the graded one.
2. **`transport_substrate_resolution`** (gene) — is the gene's substrate
   breadth meaningful. `family_inferred` means every deepest attachment is
   a lumping family: the breadth is reachability, not capability, and
   `substrate_depth=['most_specific']` does not screen such genes out
   (substrates no kept child of the superfamily carries sit
   `most_specific` at the superfamily itself).
   `resolved` means **at least one** deepest attachment is non-lumping —
   not all of them. A gene attached at both a specific family and the ABC
   superfamily is `resolved` and still carries the superfamily rollup in
   its `transported_metabolite_count`; only the row level separates them.
3. **`substrate_depth`** (transport row) — `most_specific` is the most
   specific *surviving* transporter node for this substrate relative to
   the gene-pruned hierarchy; it can be a family node when no gene in the
   KG is annotated below it, and it is not a curation level. `inherited`
   rows came down from an ancestor's substrate set. A gene can have
   several `most_specific` attachments (one per surviving branch).

Transport rows are **deepest-attachment projections**: a gene attached to
a family and to one of its descendants contributes rows only through the
descendant, so distinct genes / metabolites across the rows match the KG's
`transporter_gene_count` / `transported_metabolite_count`. Superseded
ancestor rows are intentionally absent; full family membership (ancestors
included) is visible via `gene_ontology_terms(ontology='tcdb',
include_superseded=True)`.

`metabolites_by_gene` and `genes_by_metabolite` emit an automatic warning
when inherited rows dominate (metabolite-anchored) or when input genes
read `family_inferred` (gene-anchored), and sort detail rows
metabolism → `most_specific` → `inherited`, then by score, so a single
superfamily-only gene cannot consume the `limit`. Filter with
`substrate_depth=['most_specific']` when precision matters. See
`docs://analysis/metabolites` for the full ladder.

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

## Metabolite ID forms (chemistry + metabolomics tools)

Canonical `Metabolite.id` carries a namespace prefix: `kegg.compound:C00064`,
`chebi:10004`, `mnx:MNXM…`. Every `metabolite_ids` / `exclude_metabolite_ids`
parameter on the seven chemistry / metabolomics tools (`list_metabolites`,
`genes_by_metabolite`, `metabolites_by_gene`, `list_metabolite_assays`,
`metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`,
`assays_by_metabolite`) also accepts the un-prefixed / xref aliases and
resolves them to canonical IDs before the query runs: bare KEGG `C00064`,
`CHEBI:17234` or bare numeric `17234`, `HMDB0000122`, `MNXM1095050`.
Canonical forms pass through untouched; any other prefixed form is passed
through verbatim and lands in `not_found`.

- **Collision policy.** KEGG xrefs are unique; CHEBI / HMDB / MNXM are not
  (two KEGG nodes can share one `chebi_id`). An ambiguous alias expands to
  **all** matching metabolites and appends a `warnings` entry
  (`'<input>' resolved to N metabolites: [...] — pass the canonical id to
  narrow`). Nothing is silently picked. The same rule applies to
  `exclude_metabolite_ids` — an ambiguous exclude removes every match.
- **Envelope.** Coerced inputs are reported in `resolved_aliases`
  (`{input: [canonical, ...]}`, empty when none). Unresolved inputs stay
  verbatim and appear in `not_found` in the form you passed. Exclude-wins-on-
  overlap is evaluated on the canonical IDs, so mixed forms across
  `metabolite_ids` and `exclude_metabolite_ids` still overlap correctly.
- **Not coercion:** `list_metabolites`' exact-xref filters
  (`kegg_compound_ids`, `chebi_ids`, `hmdb_ids`, `mnxm_ids`) match the xref
  property directly, never rewrite the input, and report nothing in
  `resolved_aliases`.

## Ontology term / ortholog-group ID forms

Canonical ontology term IDs and ortholog-group IDs carry a namespace prefix
(`go:0006979`, `kegg.pathway:ko00910`, `kegg.orthology:K00001`,
`pfam:PF00004`, `interpro:IPR000014`, `tcdb:3.A.1.1`, `ec:1.1.1.1`,
`cazy:GH13`, `merops.family:S33`, `ncbifam:TIGR00254`,
`cyanorak:CK_00000570`, `eggnog:COG0592@2`). `term_ids` on
`genes_by_ontology`, `ontology_term_details`, `pathway_enrichment`,
`cluster_enrichment` and `group_ids` on `genes_by_homolog_group`,
`differential_expression_by_ortholog` also accept the bare accession —
`ko00910`, `GO:0006979`, `PF00004`, `IPR000014`, `3.A.1.1`, `1.1.1.1`,
`GH13`, `S33`, `TIGR00254`, `CK_00000570`, `COG0592@2` — and coerce it to
the canonical prefixed form (a pure regex match, no query, since a bare
accession maps onto exactly one ontology or OG source) before the query
runs. Coerced inputs are reported in `resolved_aliases` (`{input:
[canonical]}`, empty when none) — same shape as the metabolite-ID
coercion above, for cross-tool consistency. On `pathway_enrichment` /
`cluster_enrichment` this key lives nested under `term_validation`
(a passthrough of `genes_by_ontology`'s validation buckets), not at the
top level. Class- and subclass-level TCDB ids (`1`, `1.A`) and bare CAZy
class ids (`GH`, `AA`) are not coerced — pass the prefixed form
(`tcdb:1.A`, `cazy:GH`). `gene_ontology_terms` does not
take `term_ids` (it is the reverse, genes → terms, lookup) and is
unaffected.

---

## Pagination

`limit` and `offset` control row pagination on every tool that
returns a `results` list. The defaults differ by surface:

- **MCP:** `limit=5` on most tools (sometimes higher). Pages must be
  walked with explicit `offset=` calls.
- **Package:** `limit=None` — returns every matching row by default.
  Set `limit=` / `offset=` explicitly if you want MCP-style paging.
  Full contract in `docs://guide/python_api`.

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

### Lockstep paging on multi-ontology calls

`search_ontology` accepts `ontology=[...]` (or `None` for all 17). The
call fans out per ontology and **`limit` / `offset` apply to each
ontology separately** — a `limit=5` call over three ontologies returns
up to 15 rows, ordered by ontology (registry order) then by score
(search) or `gene_count` (browse). The flat envelope keys
(`total_matching`, `returned`, `truncated`, `score_max`) are sums / max
across the set; `by_ontology[]` carries the per-ontology
`total_matching` / `returned` / `truncated` so you can see which
ontology still has pages left. Walk pages with the same `offset` on the
same ontology list. Lucene scores are per index, so never rank rows of
two ontologies against each other by `score`.

### Browse vs search (`search_ontology`)

`search_ontology` has two modes, chosen by whether `search_text` is
set:

- **Search** (`search_text='...'`) — Lucene over term names; rows carry
  a `score`, sorted `score DESC`; envelope `mode: "search"`.
- **Browse** (`search_text` omitted or empty) — every term of the
  ontology, sorted `gene_count DESC, id`, `score` null; envelope
  `mode: "browse"` plus `by_level[]` over the full match. Narrow with
  `level=`, a facet (`tree=` / `interpro_type=`), `min_gene_count=`,
  or `organism=` (rows gain `organism_gene_count` and the sort/filter
  switch to that organism's count). A browse that truncates without any
  narrowing filter adds a warning — it means you are paging through an
  entire ontology.

`gene_count` and `organism_gene_count` are **subtree-scoped** on both
`search_ontology` and `ontology_term_details` for hierarchical
ontologies (a parent term counts the genes of its descendants);
`direct_gene_count` (verbose on `search_ontology`, compact on
`ontology_term_details`) is the term's own edges.

Browse answers "what terms exist here and which are big"; search
answers "which term is called X". Neither traverses the hierarchy —
for a term's parents, children and bridge links use
`ontology_term_details(term_ids=[...])`. Per-ontology semantics
(identifier form, levels, what `gene_count` means there):
`docs://ontologies/{key}`, index at `docs://ontologies/index`.

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
`docs://analysis/enrichment` has the full discussion.

---

## Annotation-trust surface (ontology tools)

**15 of the 17 ontologies carry the trust surface** — every one except
`subcellular_localization` (PSORTb) / `signal_peptide_type` (SignalP). Fourteen of them own a Gene→term edge type; BRITE
inherits its trust columns from the `Gene_has_kegg_ko` edge it is reached
through. Every such gene→term row carries a **compact trust column**:
`evidence`, a five-rung ladder `curated > signature > homology >
family_inferred > domain_inferred`. `sources[]`, `evidence_score` (a
`[0, 1]` composite, only on TCDB / MEROPS / GO×3 / EC / Pfam / CAZy), and
`tier` (TCDB / MEROPS only) are verbose. Ontology-specific native scalars
— TCDB's `confidence_score` / `attachment_depth`, MEROPS's `pfam_support`
/ `best_hit_kind`, InterPro's `libraries` / `evalue`, NCBIfam's
`bit_score`, PSORTb's `localization_score`, SignalP's `signal_peptide_*`
— are verbose-only, under their own names, and **never filterable**:
their scale and direction differ across ontologies (lower e-value is
better, higher bit score is better), so no cross-ontology threshold is
safe.

**Rule of thumb.** Rank by `evidence_score` (and the gene-level
`tcdb_evidence_score_max` / `merops_evidence_score_max`), never filter it
except through `min_evidence_score`; use `evidence=` / `sources=` /
`max_tier=` to *narrow the kind* of evidence; and always pass
`interpro_type=` when enriching on InterPro (it raises otherwise).

**Strip rule.** A row only carries the trust columns its ontology owns —
`tier` never appears on a `kegg` row (KEGG has no tier axis); `interpro_type`
never appears on a `tcdb` row. Owned-but-null columns stay (a TCDB edge with
only eggNOG support carries `tier: null`, not an absent field). The rule
holds on the MCP wire as well as in the Python API, and it is the general
row convention: result rows are serialized sparsely — a key that is absent
means "not applicable to this row" (a verbose-only column on a compact
call, an axis this ontology does not carry), a key that is `null` means
"applicable, but this record has no value" (a gene with no MEROPS call
carries `merops_evidence_score_max: null`). A compact `tcdb` row from
`genes_by_ontology` is ~9 keys, a verbose one ~22. Three tools keep a
deliberately None-padded union shape instead, so their rows always carry
every column: `genes_by_metabolite` / `metabolites_by_gene` (cross-arm
fields) and `assays_by_metabolite` / `discussed_by_publication`
(polymorphic rows).

**Filters** — `sources=`, `evidence=`, `max_tier=`, `min_evidence_score=`,
`call_class=` (MEROPS-only), `interpro_type=` (InterPro-only) — default to
`None` and never narrow a result unless set. `min_evidence_score` is the
only numeric cutoff anywhere in the surface; setting it adds
`evidence_score_signals` to the envelope (the `ControlledVocabulary`-backed
composite inputs behind the score). Passing an axis an ontology doesn't
carry raises `ValueError` naming that ontology's supported axes — check
first via `list_filter_values(filter_type='trust_axes', ontology=...)`.

**Multi-ontology filter scoping** (`gene_ontology_terms`, `ontology_landscape`):
a trust filter carried by every requested ontology applies normally; carried
by some but not all applies to those and drops the rest into
`skipped_ontologies` with a warning; carried by none raises. A **facet** —
`interpro_type` for InterPro, `tree` for BRITE — behaves differently: it
narrows its own ontology and leaves the others untouched (nothing is
skipped), and raises when its owner is not in the list at all.

**Envelope rollups are full-match.** `by_evidence`, `by_tier`, `by_sources`,
`by_call_class` and `evidence_score_stats` describe every matching row, not
the page you are reading, and they are populated in compact mode — where
`tier`, `sources` and `evidence_score` are not on the row at all, the
envelope is the only place to read their distribution. On
`gene_ontology_terms` they are empty under `summary=true`, which fetches no
rows.

**Vocab-vs-pivot.** Filterable trust values (`evidence`, `sources`,
`call_class`, `interpro_type`, and the other categorical `filter_type`s on
`list_filter_values`) are read from the KG's `ControlledVocabulary` nodes,
never hard-coded. If a `ControlledVocabulary` node is missing for some edge
type, a live pivot query derives the value set instead, flagged
`source: "pivot"` plus a warning — same values, just not pre-registered.
The same rule covers non-trust closed vocabularies such as `cluster_type`.

**Vocabulary-hash warn.** The KG stamps
`Schema_info.controlled_vocabularies_hash` (sha256 over every
`ControlledVocabulary` entry's ids, values, closed/sparse flags and score
signals — descriptions excluded). `kg_release_info` compares it with the
hash the explorer was built against; a mismatch, or a KG that predates the
vocabulary contract, yields `verdict: warn` — never worse. What it means:
calls are unaffected (filters validate live, `list_filter_values` reads
live), but the value lists quoted in `docs://ontologies/{key}` pages and in
parameter descriptions were rendered from the pinned vocabulary and may be
stale. When the warn is up, trust `list_filter_values` over any quoted
list. The pin is re-set at explorer release time to equal the live KG's
hash.

Full per-ontology trust profile, the rank-vs-filter rule, MEROPS
`call_class` semantics, and why InterPro enrichment requires `interpro_type`:
`docs://analysis/annotation_evidence`.

---

## Hierarchy `level` convention (ontology tools)

For all 17 supported ontologies, `level: int` follows the same convention:

- **`level=0`** = root (broadest term).
- Higher integers = more specific.
- Tree-shaped ontologies (Cyanorak, TIGR, EC, TCDB, CAZy, BRITE within a
  tree) have exact level semantics. TIGR has exactly two levels (main
  role → sub-role).
- DAG-shaped ontologies (GO, sometimes KEGG) use min-path-from-root
  with a sparse `level_is_best_effort='true'` flag on affected terms.
- Flat ontologies (COG functional categories, NCBIfam, PSORTb
  `subcellular_localization`, SignalP `signal_peptide_type`) have
  **`level=0` only** — no hierarchy (PSORTb / SignalP: 5 terms each).
  Passing `level=1` or higher returns no rows.
- InterPro and MEROPS are hierarchical, like TCDB — InterPro rolls up
  through `Interpro_entry_is_a_interpro_entry` (and additionally facets by
  `interpro_type`, independent of `level`); MEROPS families roll up into
  clans through `Merops_family_is_a_merops_family`.

`ontology_landscape` ranks (ontology × level) combinations by
`relevance_rank` baking in genome coverage and median term size; use it
to pick a defensible level before enrichment. Flat ontologies contribute
exactly one row per organism (level=0).

### BRITE: always scope with `tree=`

BRITE is a meta-ontology of a dozen independent classification trees
(enzymes, transporters, protein families, ...; ~2,700 terms in total).
Running all-BRITE enrichment without `tree=` is dominated by the largest
tree (enzymes, ~2,100 terms), drowning smaller-tree signal. Every
BRITE-aware tool accepts `tree=` — discover valid tree names via
`list_filter_values(filter_type='brite_tree')`.

Tools that accept `tree=`: `genes_by_ontology`, `gene_ontology_terms`,
`search_ontology`, `ontology_landscape`, `pathway_enrichment`,
`cluster_enrichment`.

---

## Organism naming

`OrganismTaxon.preferred_name` is the canonical organism string (e.g.
`"Prochlorococcus MED4"`, `"Alteromonas macleodii MIT1002"`) and equals
`Gene.organism_name`. Scalar `organism=` resolves the same way on every
tool that takes it:

- **Word match.** The input is split on spaces and every word must be a
  case-insensitive substring of `preferred_name` **or** of one of the
  node's `name_synonyms` (a former species name, for instance). So
  `"MED4"`, `"med4"` and `"Prochlorococcus MED4"` all resolve; `"MED 4"`
  does not.
- **Genes required.** Only taxa with genes resolve. Genus-level nodes,
  phages and treatment-only taxa (the coculture partner named in an
  experiment but not sequenced here) never match, even by exact name.
- **Ambiguity raises.** A value that matches more than one gene-bearing
  taxon raises `ValueError` listing the candidates
  (`organism="Prochlorococcus"` on a DE tool). Add a strain token to
  narrow.

The list forms differ slightly: `organisms=[...]` (`genes_by_homolog_group`,
`differential_expression_by_ortholog`) applies the same word match per
entry and keeps every match (`"Prochlorococcus"` selects every
Prochlorococcus strain); `list_organisms(organism_names=[...])` runs the
resolver per entry and additionally accepts an exact `preferred_name` for
gene-less taxa; `list_metabolites(organism_names=[...])` is exact,
case-insensitive on `preferred_name` only — pass the full name there.

Enumerate with `list_organisms()` (48 `OrganismTaxon` nodes, 47 distinct
names, 43 with genes). One name — `Meiothermus ruber` — is carried by two
nodes, the sequenced strain and a gene-less treatment taxon; the resolver
picks the strain because of the genes gate, but if you join organism
counts in `run_cypher`, join through `Gene_belongs_to_organism`, never
by name.

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

The KG build replaces reserved characters before loading: an apostrophe
in a name is stored as a caret (`^`) and a pipe as a comma. A `search_text`
or `run_cypher` literal containing `'` will therefore miss — search on
the surrounding words instead.
