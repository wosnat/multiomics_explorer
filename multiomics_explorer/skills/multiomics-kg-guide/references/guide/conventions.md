# Cross-tool conventions

Patterns that hold across most or all 42 tools — things you'd otherwise
re-learn tool by tool.

Node/edge meanings: `docs://guide/concepts`. Tool-by-tool routing
(families, decision tree, discover → drill table): `docs://guide/start_here`.
Python package (pagination defaults, return shapes, DataFrames):
`docs://guide/python_api`.

> **Numbers in example responses are illustrative snapshots** — one KG
> build's shape, not current values. For real counts, run the call.

**Contents:** Response shape · Filter semantics · Partial-failure buckets
· Empty per-gene results · Tested-absent rows · Annotation quality `[AQ]`
· Informative-only filtering `[ENR]` · DM family gating · Chemistry
conventions · Ontology/OG ID forms · Pagination · Background semantics ·
Trust surface summary · Hierarchy `level` convention · Organism naming ·
Score fields.

---

## Response shape: envelope + results

Every tool that returns a list of entities uses the same shape:

```
{
  "total_matching": <int>,      ← pre-pagination match count
  "returned": <int>, "truncated": <bool>, "offset": <int>,
  "by_organism": [...], "by_<dim>": [...], "top_<thing>": [...],  ← rollups, vary by tool
  "score_max": <float|None>, "score_median": <float|None>,        ← when search_text used
  "not_found": [...] | {...}, "not_matched": [...],  ← shape varies, see "Partial-failure buckets"
  "warnings": [...],            ← soft diagnostics
  "resolved_aliases": {...},    ← chemistry / metabolomics tools only
  "excluded_derived_metrics" / "excluded_assays": [...],  ← DM / assay drill-downs only
  "skipped_ontologies": [...],  ← multi-ontology term tools only
  "results": [ {...}, {...} ],  ← per-row detail
}
```

The **envelope** is the top-level dict minus `results`. Envelope rollups
(`by_*`, `top_*`, `*_count`, `score_*`) are computed over the **full
matched set**, independent of `limit`/`offset` — use them as the recon
view. Per-row **results** give detail; pagination via `limit` (default 5
on most tools) and `offset`.

### Breakdown caps on detail calls

`by_*` / `top_*` envelope lists longer than a handful of entries are
capped to the **first 10** (desc by ranking count) on a detail call
(`summary=False`, default). A capped list gets a sparse sibling key
`<key>_truncated: true`; otherwise absent in Python / `null` over MCP
(Pydantic declares every `Optional` field, so FastMCP always fills the
key). `summary=True` always returns the **full, uncapped** list — read it
first for a whole ranking (on `resolve_gene` the `by_organism` counts
then sum exactly to `total_matching`; on `list_publications` a
multi-organism paper counts once per organism). Affects rollups on the list/discovery and
drill-down tools (`list_experiments`, `list_organisms`,
`genes_by_function`, `genes_by_metabolite`, `metabolites_by_gene`,
`differential_expression_by_{gene,ortholog}`, `pathway_enrichment`,
`resolve_gene`, `list_publications` — check a specific tool's docs for
which keys). Exception: `pathway_enrichment.top_pathways_by_padj` is a
genuine top-10 in both modes, no `_truncated` companion key.

### `summary=True` mode

**36 of 42 tools accept `summary=True`** — nearly universal. It returns
only the envelope (`results=[]`, `returned=0`; `truncated` is `true`
whenever rows were withheld and `false` when nothing matched). Use it as the **first call** for any
question that doesn't already specify exact IDs. Pattern: `summary=True`
→ narrow filters → drop `summary=True` for detail. Exception: on
`metabolites_by_gene` the envelope is computed over the whole locus-tag
batch, so `summary=True` on 50+ genes costs as much as a detail call —
use it because the envelope is the artifact, not to save time.

The 6 tools without `summary=` — `kg_schema`, `kg_release_info`,
`ontology_term_details`, `list_filter_values`, `gene_response_profile`,
`run_cypher` — either return small fixed sets, are themselves summaries,
take a bounded batch, or have raw / shape-specific output.

### `warnings`: advisory diagnostics

`warnings` (`list[str]`, always present, `[]` when clean) surfaces a
closed-vocabulary filter value that matched no `ControlledVocabulary`
entry, an unmatched `organism` word, a rankable/has_p_value gate
exclusion, an ID collision, a case-only `not_found` typo (most per-gene
batch tools check this), and similar. **Advisory only — never changes
which rows come back**; the call still runs against whatever the filters
matched, it just tells you *why*. Each warning names the tool to call for
the valid set — `list_filter_values(filter_type=...)` for a vocabulary
typo, `list_organisms()` for an unmatched organism.

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

- **ID-batch filters** (`metabolite_ids`, `experiment_ids`, `locus_tags`,
  `term_ids`, `group_ids`, ...) — **UNION**: a row matches if it has ANY
  of the listed IDs. Combined with other filters via AND.
- **Element-presence filters** (`elements=["N", "P"]`,
  `metabolite_elements=["N"]`) — **AND-of-presence**: every listed
  element must be present.
- **Categorical-set filters** (`evidence_sources`, `gene_categories`,
  `categories`, `metabolite_pathway_ids`) — **set-membership ANY**: a row
  passes if its values overlap the filter.
- **`exclude_metabolite_ids`** — **set-difference**, exclude wins on
  overlap with `metabolite_ids`; empty list is a no-op. Present on all
  seven chemistry / metabolomics tools, typically used to strip currency
  cofactors (ATP, NADH, water). Accepts the same alias forms as
  `metabolite_ids` — `docs://analysis/metabolites`.
- **Controlled-vocabulary filters** (`treatment_type`, `background_factors`,
  `compartment`, `growth_phases`, `omics_type`, `cluster_type`, the trust
  vocabularies) match exact values. An unknown value returns 0 rows, not
  an error — read the live set with `list_filter_values(filter_type=...)`
  before guessing a spelling.

When in doubt, the tool's parameter description states the semantics
explicitly.

### Single-organism vs cross-organism

Three shapes of organism scope exist; all scalar `organism=` values go
through the same resolver (see "Organism naming" below). **Required
scalar `organism=`** (omitting raises, list raises) — needs one gene
universe (TERM2GENE mapping, background, single-organism chemistry join):
`genes_by_ontology`, `gene_ontology_terms`, `ontology_landscape`,
`pathway_enrichment`, `cluster_enrichment`, `genes_by_metabolite`,
`metabolites_by_gene`. **Optional scalar `organism=`, single organism
enforced** — inferred from input IDs when omitted, raises if they span
more than one organism: `differential_expression_by_gene`,
`gene_response_profile`, `gene_derived_metrics`, `gene_clusters_by_gene`,
`genes_in_cluster`. **Cross-organism** — rows from any organism;
`organism=` / `organisms=[...]` is an optional narrowing filter on the
remaining discovery / drill-down tools; list `organism_names=[...]` is
**only** on `list_organisms` and `list_metabolites` (unknown names land
in `not_found`); a handful of gene-batch tools
(`gene_overview`, `gene_details`, `gene_homologs`, `gene_aa_sequence`,
`gene_neighbors`, `search_homolog_groups`, `discussed_by_publication`)
take no organism parameter at all (gene rows still carry per-row
`organism`).

The pattern: anything needing a precomputed organism-scoped index
(ontology terms, backgrounds, chemistry joins) is single-organism;
anything summarizing or comparing across organisms is cross-organism. See
"Organism naming" below for `coculture_partner=`. Per-row routing signals
on discovery tools (`expression_edge_count`, `catalyst_gene_count`,
`evidence_sources`, `rankable`, ...) tell you which drill-downs are
productive — `docs://guide/start_here` lists the pairs.

---

## Partial-failure buckets: `not_found` vs `not_matched`

Most batch tools surface two kinds of partial failure rather than
raising: **`not_found`** — the input ID doesn't exist in the KG at all
(almost always a typo/stale ID); **`not_matched`** — the ID exists but
has no edge to the target after filters (e.g. a locus_tag in a different
organism, a DOI naming no genes/pathways in prose) — the row exists, but
the question doesn't apply.

The **key shape** depends on how many ID batches the tool accepts:

| Shape | Used by |
|---|---|
| Flat `not_found: list[str]` (+ flat `not_matched` where distinguished) — one input batch | most single-batch tools, e.g. `gene_overview`, `gene_ontology_terms`, `genes_by_ontology`, `pathway_enrichment`, `list_organisms`, `list_publications`, `gene_response_profile` — check a tool's own docs |
| Dict keyed by input bucket — `not_found.metabolite_ids`, `.assay_ids`, ... (only accepted buckets) | the six multi-batch chemistry / metabolomics tools: `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`, `list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay` |
| Suffixed flat lists — `not_found_<bucket>` / `not_matched_<bucket>` | `genes_by_homolog_group` (`_groups`, `_organisms`), `differential_expression_by_ortholog` (`_groups`, `_organisms`, `_experiments`), `differential_expression_by_gene` (`not_found` + `_experiments`), `genes_in_cluster` (`_clusters`, `not_matched_organism`), `genes_by_{numeric,boolean,categorical}_metric` (`_ids`, `_metric_types`, `not_matched_organism`) |
| tool-specific diagnostic buckets — `wrong_ontology`, `wrong_level`, `filtered_out`; `no_expression`, `not_found_experiments`; `no_groups` | `genes_by_ontology`, `differential_expression_by_gene`, `gene_response_profile`, `gene_homologs` |

E.g. `gene_overview(locus_tags=["PMM0001","NOPE"])` → `not_found:
["NOPE"]`. Tools with no ID batch (`genes_by_function`, `search_ontology`,
`search_homolog_groups`, `list_clustering_analyses`, `list_derived_metrics`,
`resolve_gene`) have no `not_found` — an empty `results` is simply no
match.

Always inspect both buckets. An empty `results` plus a populated
`not_found` or `not_matched` is *not* "no biology" — it's a routing
problem.

---

## Empty per-gene results: "no hit" vs "out of scope"

A per-gene tool returning nothing for a gene (`gene_homologs`
`no_groups`, `gene_ontology_terms` zero rows, `gene_clusters_by_gene` /
`gene_derived_metrics` `not_matched`) does **not** by itself mean the
biology is absent. Three cases collapse into "empty": ran but found
nothing ("no hit"); the source never applied to this gene ("out of
scope"); the gene isn't in the KG (`not_found` — distinguished above).

Don't read an empty result as a biological negative. The actionable
signal is on `gene_overview`: **`annotation_state`** (`no_evidence` /
`catch_all_only` / `informative_single` / `informative_multi`) tells you
whether the gene has informative evidence at all. For the rarer
"ran-but-empty vs never-ran" distinction, `gene_details.contributing_sources`
lists the 9 pipelines that contributed at least one field (`ncbi`,
`uniprot`, `cyanorak`, ..., `merops_diamond`).

**Cross-organism caveat:** `cyanorak`-derived annotations (Cyanorak
roles, curated products, many ortholog groups) apply to
**Prochlorococcus / Synechococcus only**. Heterotroph genes
(Alteromonas, Pseudomonas, Marinobacter, Meiothermus, …) lack them **by
design** — don't infer "poorly annotated" from missing Cyanorak /
ortholog coverage on a heterotroph.

---

## Tested-absent rows are real biology

In the metabolomics layer (`MetaboliteAssay` edges), the KG stores
**tested-and-not-detected** rows alongside tested-and-detected ones:
`Assay_quantifies_metabolite.detection_status ∈ {detected, not_detected,
...}` (about 70% of numeric edges are `not_detected`) and
`Assay_flags_metabolite.flag_value` (`detected`/`not_detected` in the KG,
surfaced as `True`/`False`; about 69% of boolean edges are `False`). Both
are a deliberate biological signal — looked for and not found, in
contrast to "not measured at all".

**Tools default to keeping tested-absent rows.** Filter them out only
when you have a specific reason. Envelope rollups
(`by_detection_status`, `by_flag_value`) surface this composition as
the primary headline. See `docs://analysis/metabolites`.

### Expression: `table_scope` decides what absence means

The expression layer (`Changes_expression_of` edges) has the same
question — tested-and-not-significant, or never reported? — but the
answer depends on the parent experiment's `table_scope`:

- `table_scope='all_detected_genes'` — the paper reported every
  detected gene including non-significant ones. Tested-absent rows are
  present (`expression_status='not_significant'`); a gene with no edge
  means truly not detected.
- Any other scope (`significant_only`, `significant_any_timepoint`,
  `filtered_subset`, `top_n`) — the paper reported only a subset;
  tested-absent collapses with not-detected and you can't tell which
  from the KG.

Always check the experiment's `table_scope` (on `list_experiments` and
the per-row context of `differential_expression_by_gene`) before drawing
conclusions from missing rows — the same gene can carry both shapes
across different experiments. `table_scope` is **sparse**: a
characterization study (mRNA decay, promoter mapping) or a
metabolomics-only experiment carries no `table_scope` property at all,
never an empty string, and `table_scope=[...]` filters never match it.

### Dense experiment metadata

**`treatment_type` is dense and never empty** on every `Experiment`,
`ClusteringAnalysis`, `DerivedMetric` and `MetaboliteAssay` — a study with
no perturbation names *what was measured* instead (`rna_decay`,
`tss_mapping`, `genomic_analysis`); filter on those to isolate
characterization studies, never test for `[]`. `background_factors` is
likewise dense on `Experiment`; `[]` only on sequence-only clustering
analyses. **`growth_phases` is an open vocabulary** — enumerate live via
`list_filter_values(filter_type='growth_phase')`; `treatment_type`,
`cluster_type` and the trust vocabularies are closed.

### Two-state strings

Boolean-like properties are stored as **two-state strings** in the KG
(`Experiment.is_time_course`: `time_course` / `single_time_point`;
`DerivedMetric.rankable`: `rankable` / `not_rankable`;
`DerivedMetric.has_p_value`: `p_value` / `no_p_value`;
`Derived_metric_flags_gene.value`: `flagged` / `not_flagged`;
`Assay_flags_metabolite.flag_value`: `detected` / `not_detected`). Tool
parameters and most output columns stay `bool`; a couple of rollups
surface the KG literal instead. Tested-absent (`not_flagged`) edges exist
on only 11 of 27 boolean DMs — the rest are positive-only, so
`genes_by_boolean_metric(flag_value=False)` is DM-dependent (read
`by_metric[*].false_count`). `Assay_flags_metabolite` always stores both
states.

---

## Annotation quality (`[AQ]` footnote)

`Gene.annotation_quality` is a 0..3 numeric encoding of
`Gene.annotation_state` (informative-evidence count): `0` = `no_evidence`,
`1` = `catch_all_only` (catch-all name/product), `2` = `informative_single`,
`3` = `informative_multi`. `min_quality=2` skips hypothetical proteins;
`min_quality=3` for high-confidence gene sets.

**Drift caveat.** Earlier KG releases encoded product-name quality in the
same field — old `min_quality` filters now silently select a different
gene set, with no deprecation warning. Affected tools:
`genes_by_function`, `gene_details`, `gene_overview`, plus any tool
filtering on `annotation_quality`.

---

## Informative-only filtering on enrichment + ontology (`[ENR]` footnote)

`pathway_enrichment`, `cluster_enrichment` and `ontology_landscape`
default to `informative_only=True`: uninformative ontology terms
(`is_uninformative='true'` in the KG) are excluded from the Fisher tests
and the landscape ranking; per-row `is_informative` is surfaced
regardless, so you can post-filter. `search_ontology`, `genes_by_ontology`
and `gene_ontology_terms` default to `informative_only=False` — a lookup
should not hide what a gene is annotated to; pass `informative_only=True`
there for the enrichment-eligible subset only.

**What is flagged.** Set per ontology by the KG build. GO roots
(`go:0008150` "biological_process" and siblings) are flagged. In KEGG,
KO-level catch-alls and the global/overview maps (11 of the 13
parentless pathway nodes) are flagged; Nitrogen-cycle and Sulfur-cycle
maps stay informative, and category/subcategory nodes are never flagged
(gate those with `level`). KEGG pathway IDs are always `kegg.pathway:ko…`
— no `map…` form. Which terms an ontology flags and why:
`docs://ontologies/{key}` "Informativeness rule".

**Reproducibility caveat.** BH-adjusted p-values depend on the term set
tested in each cluster — runs including uninformative terms differ from
runs excluding them, even on identical inputs (the raw `pvalue` is
unaffected). For locked baselines, pass `informative_only=False` and
post-filter on `is_informative`. Full methodology:
`docs://analysis/enrichment`.

---

## DM family gating

The DerivedMetric drill-down tools (`genes_by_numeric_metric`,
`genes_by_boolean_metric`, `genes_by_categorical_metric`) accept some
filters that only apply to specific DM subsets. Consistent contract
across all three: **always-available filters** (raw value, flag,
category) work on every selected DM; **rankable-gated filters**
(`metric_bucket`, `min_percentile` / `max_percentile`, `max_rank` —
populating row fields `metric_bucket`, `metric_percentile`,
`rank_by_metric`) only apply on DMs with `rankable=True` — mixed input
soft-excludes non-rankable DMs into `excluded_derived_metrics` +
`warnings`, all-non-rankable input raises; **`has_p_value`-gated
filters** (`significant_only`, `max_adjusted_p_value`) are analogous,
raising when no selected DM carries p-values.

Inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories`
on `list_derived_metrics` before drill-down. Same shape applies to
`metabolites_by_quantifies_assay` (`rankable` on `MetaboliteAssay`,
exclusions in `excluded_assays`).

---

## Chemistry conventions

The chemistry / metabolomics surface (`list_metabolites`,
`genes_by_metabolite`, `metabolites_by_gene`, and the four metabolomics
tools) has three cross-cutting conventions: a three-level transport trust
ladder (`tcdb_evidence_score` → `transport_substrate_resolution` →
`substrate_depth`) for TCDB-derived substrate calls, permanent
direction-agnosticism on KEGG reaction joins, and a bare/xref coercion
scheme for `metabolite_ids` (bare KEGG, `CHEBI:`, `HMDB`, `MNXM` all
resolve to the canonical `kegg.compound:` / `chebi:` / `mnx:` form). Full
detail: `docs://analysis/metabolites`.

## Ontology term / ortholog-group ID forms

Canonical ontology term / OG IDs carry a namespace prefix (`go:0006979`,
`kegg.pathway:ko00910`, `pfam:PF00004`, `tcdb:3.A.1.1`, `ec:1.1.1.1`,
`cazy:GH13`, `merops.family:S33`, `ncbifam:TIGR00254`,
`cyanorak:CK_00000570`, `eggnog:COG0592@2`). `term_ids` (on
`genes_by_ontology`, `ontology_term_details`, `pathway_enrichment`,
`cluster_enrichment`) and `group_ids` (on `genes_by_homolog_group`,
`differential_expression_by_ortholog`) also accept the bare accession
(`ko00910`, `GO:0006979`, `PF00004`, ...) and coerce it to canonical
(regex match — a bare accession maps onto exactly one ontology/OG source)
before the query runs. Coerced inputs land in `resolved_aliases`
(`{input: [canonical]}`, empty when none; nested under `term_validation`
on the two enrichment tools). Class/subclass-level TCDB ids (`1`, `1.A`)
and bare CAZy class ids (`GH`, `AA`) are not coerced — pass the prefixed
form. `gene_ontology_terms` does not take `term_ids` (reverse lookup).

---

## Pagination

`limit` and `offset` control row pagination on every tool that returns a
`results` list. **MCP** defaults `limit=5` (sometimes higher), walked with
explicit `offset=` calls; **Package** defaults `limit=None` (returns
every matching row) — set `limit=` / `offset=` explicitly for MCP-style
paging, full contract in `docs://guide/python_api`.

`total_matching` is the **pre-pagination** count of all matching rows;
`returned` is the current page's size; `truncated=True` means more rows
exist beyond `offset + returned`.

**Envelope rollups are computed over the full matched set, not the
current page** — `by_organism`, `by_metric`, `top_*`, `score_max`, etc.
are identical across pages of the same query. This is deliberate: the
envelope is the recon view, designed to characterize the slice before you
commit to paginating its details.

### Lockstep paging on multi-ontology calls

`search_ontology` accepts `ontology=[...]` (or `None` for all 17) and
fans out per ontology; **`limit` / `offset` apply to each ontology
separately** — a `limit=5` call over three ontologies returns up to 15
rows. Flat envelope keys are sums / max across the set; `by_ontology[]`
carries the per-ontology breakdown. Walk pages with the same `offset` on
the same ontology list. Lucene scores are per index — never rank rows of
two ontologies against each other by `score`.

### Browse vs search (`search_ontology`)

Two modes, chosen by whether `search_text` is set: **Search**
(`search_text='...'`) — Lucene over term names, rows carry `score` sorted
desc, envelope `mode: "search"`. **Browse** (omitted/empty) — every term,
sorted `gene_count DESC, id`, `score` null, envelope `mode: "browse"` plus
`by_level[]`; narrow with `level=`, a facet (`tree=` / `interpro_type=`),
`min_gene_count=`, or `organism=` (rows gain `organism_gene_count`). A
browse that truncates without a narrowing filter adds a warning.

`gene_count` / `organism_gene_count` are **subtree-scoped** for
hierarchical ontologies; `direct_gene_count` is the term's own edges.
Browse answers "what terms exist and which are big"; search answers
"which term is called X". Neither traverses the hierarchy — use
`ontology_term_details(term_ids=[...])` for parents/children/bridges.
Per-ontology semantics: `docs://ontologies/{key}`, index at
`docs://ontologies/index`.

---

## Background semantics for enrichment

`pathway_enrichment` and `cluster_enrichment` accept three background
modes: **`table_scope`** (default for `pathway_enrichment`) — per-cluster
background = the gene universe quantified in that experiment, for a gene
set that came from a DE table; **`cluster_union`** (default for
`cluster_enrichment`) — all genes in the parent ClusteringAnalysis;
**`organism`** — full organism gene set, for whole-genome analyses not
tied to a quantification table. A **custom list** (`list[str]` of
locus_tags) is also accepted as `background=`.

The choice of background matters more than the choice of ontology.
`docs://analysis/enrichment` has the full discussion.

---

## Trust surface summary (ontology tools)

**15 of the 17 ontologies carry the trust surface** — every one except
`subcellular_localization` (PSORTb) / `signal_peptide_type` (SignalP).
Every gene→term row on the other 15 carries a compact `evidence` column
(five-rung ladder) plus verbose `sources[]` / `evidence_score` / `tier`;
native scalars (TCDB's `confidence_score`, MEROPS's `pfam_support`,
InterPro's `evalue`, ...) are verbose-only and never filterable — scale
and direction differ across ontologies, so no cross-ontology threshold is
safe. Rank by `evidence_score` (filter only via `min_evidence_score`); use
`evidence=` / `sources=` / `max_tier=` to narrow the *kind* of evidence;
pass `interpro_type=` whenever enriching on InterPro (it raises
otherwise). Full per-ontology trust profile, the rank-vs-filter rule, the
sparse-row convention, MEROPS `call_class`, and why InterPro enrichment
requires `interpro_type`: `docs://analysis/annotation_evidence`.

---

## Hierarchy `level` convention (ontology tools)

For all 17 supported ontologies, `level: int` follows the same convention:
**`level=0`** = root (broadest term), higher integers = more specific.
Tree-shaped ontologies (Cyanorak, TIGR, EC, TCDB, CAZy, BRITE within a
tree) have exact level semantics (TIGR: exactly two, main role →
sub-role). DAG-shaped ontologies (GO, sometimes KEGG) use
min-path-from-root, with a sparse `level_is_best_effort='true'` flag on
affected terms. Flat ontologies (COG functional categories, NCBIfam,
PSORTb `subcellular_localization`, SignalP `signal_peptide_type`) have
**`level=0` only** — `level=1` or higher returns no rows. InterPro and
MEROPS are hierarchical like TCDB — InterPro rolls up through
`Interpro_entry_is_a_interpro_entry` (facets separately by
`interpro_type`); MEROPS families roll up into clans.

`ontology_landscape` ranks (ontology × level) combinations by
`relevance_rank`, baking in genome coverage and median term size; use it
to pick a defensible level before enrichment. Flat ontologies contribute
exactly one row per organism (level=0).

### BRITE: always scope with `tree=`

BRITE is a meta-ontology of a dozen independent classification trees
(~2,700 terms total). Running all-BRITE enrichment without `tree=` is
dominated by the largest tree (enzymes, ~2,100 terms), drowning
smaller-tree signal. Every BRITE-aware tool (`genes_by_ontology`,
`gene_ontology_terms`, `search_ontology`, `ontology_landscape`,
`pathway_enrichment`, `cluster_enrichment`) accepts `tree=` — discover
valid names via `list_filter_values(filter_type='brite_tree')`.

---

## Organism naming

`OrganismTaxon.preferred_name` is the canonical organism string (e.g.
`"Prochlorococcus MED4"`) and equals `Gene.organism_name`. Scalar
`organism=` resolves the same way everywhere: **word match** — every
space-split input word must be a case-insensitive substring of
`preferred_name` or a `name_synonym` (`"MED4"`, `"med4"`,
`"Prochlorococcus MED4"` all resolve; `"MED 4"` does not); **genes
required** — genus-level nodes, phages and treatment-only taxa (a
coculture partner not sequenced here) never match, even by exact name;
**ambiguity raises** `ValueError` listing candidates
(`organism="Prochlorococcus"` on a DE tool) — add a strain token to
narrow.

The list forms differ slightly: `organisms=[...]` (`genes_by_homolog_group`,
`differential_expression_by_ortholog`) keeps every match per entry
(`"Prochlorococcus"` selects every strain); `list_organisms(organism_names=[...])`
additionally accepts an exact `preferred_name` for gene-less taxa;
`list_metabolites(organism_names=[...])` is exact, case-insensitive on
`preferred_name` only.

Enumerate with `list_organisms()` (48 `OrganismTaxon` nodes, 47 distinct
names, 43 with genes). One name — `Meiothermus ruber` — is carried by two
nodes (sequenced strain + gene-less treatment taxon); the resolver picks
the strain, but joins over `run_cypher` should go through
`Gene_belongs_to_organism`, never by name.

`organism=` filters the **profiled organism only** on tools where it
applies (`list_experiments`, `differential_expression_by_gene`). For
coculture-partner-side filtering use `coculture_partner=` — the two
fields are distinct.

---

## Score fields (Lucene search)

Tools with `search_text=` parameters use a Neo4j fulltext index and
return Lucene relevance scores: each row carries `score: float`; the
envelope carries `score_max` / `score_median` (`float | None`); results
sort by score desc by default; Lucene syntax is supported (boolean
operators, phrase matching, fuzzy `~`, field-boosting), e.g.
`search_text="phosphate AND (transporter OR permease)"`. Tools with
`search_text=`: `genes_by_function`, `search_ontology`,
`list_metabolites`, `list_experiments`, `list_publications`, + 4 more.

The KG build replaces reserved characters before loading: an apostrophe
becomes a caret (`^`), a pipe becomes a comma. A `search_text` or
`run_cypher` literal containing `'` will therefore miss — search on the
surrounding words instead.
