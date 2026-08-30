# Pathway Enrichment Methodology

**Served as:** `docs://analysis/enrichment`  
**Runnable examples:** `docs://examples/pathway_enrichment.py`
(`--scenario landscape | de | cluster | ortholog | custom`)

How to run over-representation analysis (ORA) with the `multiomics_explorer`
package: the building blocks, one worked recipe per gene-set source (DE,
cluster membership, ortholog groups, custom lists), background choice,
informativeness and trust filters, interpretation, and the field reference.
Every Python block below runs as written against the live KG; the example
script is the same code with output.

For the MCP wrappers see `docs://tools/pathway_enrichment` and
`docs://tools/cluster_enrichment`.

---

## 1. What enrichment is

Given a **gene set** (for example the significant DE genes of one experiment ×
timepoint × direction) and a **background** (the genes that could have appeared
in that set), ORA asks which functional terms are more represented in the gene
set than chance predicts. The test is a one-sided Fisher exact test per
(gene set, term) pair, Benjamini-Hochberg corrected within each gene set.

The primitive (`fisher_ora`) is gene-list-first: it knows nothing about
experiments or the KG. It takes any gene sets, any backgrounds, any TERM2GENE
mapping. The DE-wired and cluster-wired paths (including both MCP tools) are
convenience layers on top of it.

---

## 2. Building blocks

All names are importable from the top-level `multiomics_explorer` namespace
(`docs://guide/python_api`).

```python
from multiomics_explorer import (
    EnrichmentInputs, fisher_ora, signed_enrichment_score,
    de_enrichment_inputs, cluster_enrichment_inputs,
    pathway_enrichment, cluster_enrichment,
    genes_by_ontology, ontology_landscape, to_dataframe,
)
```

| Name | Role |
|---|---|
| `EnrichmentInputs(organism_name, gene_sets, background, cluster_metadata, ...)` | Pydantic bundle. `gene_sets` and `background` are both `dict[str, list[str]]` keyed by gene-set name (`cluster` in the output) — a background is **per gene set**, never one shared list. `cluster_metadata` is `dict[str, dict]` with the same keys; pass `{name: {}}` when there is no context. |
| `fisher_ora(inputs, term2gene, *, min_gene_set_size=5, max_gene_set_size=500)` | The Fisher + BH primitive. Returns `EnrichmentResult`. There is no `background` parameter — it reads `inputs.background`. |
| `de_enrichment_inputs(experiment_ids, organism, direction='both', significant_only=True, timepoint_filter=None, growth_phases=None)` | Calls `differential_expression_by_gene`, partitions rows into gene sets named `"{experiment_id}|{timepoint}|{direction}"`, and sets per-set `table_scope` backgrounds plus `not_found` / `not_matched` / `no_expression` buckets. |
| `cluster_enrichment_inputs(analysis_id, organism, min_cluster_size=3, max_cluster_size=None)` | Calls `genes_in_cluster(analysis_id=...)`, one gene set per cluster, `cluster_union` background, `clusters_skipped` for size-filtered clusters, `analysis_metadata`. |
| `genes_by_ontology(ontology, organism, level=None, term_ids=None, ...)` | The canonical TERM2GENE source; `to_dataframe()` of its result has the required `term_id`, `term_name`, `locus_tag` columns. Pass `min_gene_set_size=0, max_gene_set_size=None, limit=None` so the size filter is applied once, by `fisher_ora`, against each gene set's own background. |
| `signed_enrichment_score(df, direction_col='direction', padj_col='p_adjust')` | Collapses `|up` / `|down` pairs into one row per (stem, term); score is `sign × −log10(min p_adjust)`. |
| `pathway_enrichment(...)` / `cluster_enrichment(...)` | The two wrappers: inputs helper → `genes_by_ontology` → `fisher_ora` → metadata merge → `EnrichmentResult` with `params`. |

**`ontology` keys.** GO is three ontologies (`go_bp`, `go_mf`, `go_cc`); there
is no `"go"`. `list_filter_values` does not enumerate them — the 17 keys are in
`docs://ontologies/index`. `level` follows the hierarchy convention (0 = root,
higher = more specific; `docs://guide/conventions`).

---

## 3. Scout first — `ontology_landscape`

```python
from multiomics_explorer import list_experiments, ontology_landscape, to_dataframe

exp = list_experiments(organism="MED4", omics_type=["RNASEQ"],
                       treatment_type=["nitrogen"], limit=None)
experiment_ids = [r["experiment_id"] for r in exp["results"]
                  if (r["distinct_gene_count"] or 0) >= 500]

landscape = ontology_landscape(organism="MED4", experiment_ids=experiment_ids,
                               min_gene_set_size=5, max_gene_set_size=500, limit=None)
df = to_dataframe(landscape)
df.sort_values("relevance_rank")[
    ["ontology_type", "level", "relevance_rank", "genome_coverage",
     "median_genes_per_term", "n_terms_with_genes"]
].head(10)
```

Rows are (ontology × level) — the column is `ontology_type`. `relevance_rank`
(1 = best) bakes in `genome_coverage` and `median_genes_per_term`; passing
`experiment_ids` adds experiment-weighted coverage columns. For MED4 the top
ranks are `tigr_role` 1, `cyanorak_role` 1, `go_mf` 2, `go_bp` 3. GO rows also
carry `best_effort_share` — the fraction of terms whose depth is a min-path
proxy because GO is a DAG (section 10).

BRITE and InterPro rows are broken down per `tree` / `interpro_type`
because each tree or type is a separate universe (section 8).

---

## 4. DE path (what `pathway_enrichment` does)

```python
from multiomics_explorer import (
    de_enrichment_inputs, fisher_ora, signed_enrichment_score,
    genes_by_ontology, to_dataframe,
)

inputs = de_enrichment_inputs(
    experiment_ids=experiment_ids, organism="MED4",
    direction="both", significant_only=True,
)
# inputs.gene_sets      {"<exp>|<timepoint>|up": [...], "<exp>|<timepoint>|down": [...]}
# inputs.background     same keys -> the experiment's quantified genes (table_scope)
# inputs.cluster_metadata[name]["direction"], ["experiment_id"], ["timepoint"], ...
# inputs.not_found / not_matched / no_expression   -> experiment-level buckets

term2gene = to_dataframe(genes_by_ontology(
    ontology="go_bp", organism="MED4", level=3,
    min_gene_set_size=0, max_gene_set_size=None, limit=None,
))
result = fisher_ora(inputs, term2gene, min_gene_set_size=5, max_gene_set_size=500)

df = result.results.copy()
df["direction"] = df["cluster"].map(lambda c: inputs.cluster_metadata[c]["direction"])
collapsed = signed_enrichment_score(df)   # one row per (experiment|timepoint, term)
```

The wrapper does exactly this, then merges `cluster_metadata` onto the rows,
adds `signed_score`, records `result.params`, and fills `clusters_skipped`:

```python
from multiomics_explorer import pathway_enrichment

result = pathway_enrichment(
    organism="MED4", experiment_ids=experiment_ids,
    ontology="go_bp", level=3, direction="both",
)
result.results.head()                        # 1,242 rows over 20 gene sets on the live KG
first = result.results.iloc[0]
result.explain(first["cluster"], first["term_id"])._repr_markdown_()
result.to_compare_cluster_frame().head()     # clusterProfiler compareCluster columns
result.generate_summary()["n_significant"]
result.to_envelope(limit=5)["truncated"]
```

Prefer the wrapper when the gene sets come from DE tables; drop to the
primitives when you need to edit the gene sets or the TERM2GENE frame between
steps.

---

## 5. Cluster-membership path (non-DE)

`genes_in_cluster` rows are **per gene** (`cluster_id`, `cluster_name`,
`locus_tag`, ...). `cluster_enrichment_inputs` does the grouping for you and
builds the `cluster_union` background (every gene in any cluster of the
analysis, including clusters later dropped by the size filter):

```python
from multiomics_explorer import (
    list_clustering_analyses, cluster_enrichment_inputs, cluster_enrichment,
    genes_by_ontology, fisher_ora, to_dataframe,
)

analyses = list_clustering_analyses(organism="MED4", limit=None)
analysis_id = next(r["analysis_id"] for r in analyses["results"]
                   if "nstarvation" in r["analysis_id"])
# clustering_analysis:msb4100087:med4_kmeans_nstarvation — 9 clusters, 410 genes

inputs = cluster_enrichment_inputs(analysis_id=analysis_id, organism="MED4")
# inputs.gene_sets           {cluster_name: [locus_tags]}     (9 sets)
# inputs.background          {cluster_name: cluster_union}    (410 genes each)
# inputs.clusters_skipped    [{cluster_id, cluster_name, member_count, reason}]
# inputs.analysis_metadata   {analysis_id, analysis_name, cluster_type, ...}

term2gene = to_dataframe(genes_by_ontology(
    ontology="cyanorak_role", organism="MED4", level=1,
    min_gene_set_size=0, max_gene_set_size=None, limit=None,
    informative_only=True,          # what the wrapper passes by default
))
manual = fisher_ora(inputs, term2gene)

wrapped = cluster_enrichment(analysis_id=analysis_id, organism="MED4",
                             ontology="cyanorak_role", level=1)
assert len(manual.results) == len(wrapped.results)    # 198 rows on the live KG
```

If you group the rows yourself, key on `cluster_id` (or `cluster_name`), not on
a `genes` list — no such field exists.

---

## 6. Ortholog-group path (non-DE)

`genes_by_homolog_group` rows are per gene too (`group_id`, `locus_tag`,
`organism_name`). Most groups have one member per organism, so pool the groups
that answer your question into one gene set and test against the organism gene
universe:

```python
from multiomics_explorer import (
    search_homolog_groups, genes_by_homolog_group, run_cypher,
    EnrichmentInputs, genes_by_ontology, fisher_ora, to_dataframe,
)

groups = search_homolog_groups(search_text="transporter", limit=100)
members = genes_by_homolog_group(
    group_ids=[r["group_id"] for r in groups["results"]],
    organisms=["MED4"], limit=None,
)
gene_set = sorted({r["locus_tag"] for r in members["results"]})

# Organism gene universe — list_organisms does not carry locus_tags.
universe = sorted(r["locus_tag"] for r in run_cypher(
    "MATCH (g:Gene {organism_name: 'Prochlorococcus MED4'}) "
    "RETURN g.locus_tag AS locus_tag"
)["results"])                                   # 1,973 genes

inputs = EnrichmentInputs(
    organism_name="MED4",
    gene_sets={"transporter_orthologs": gene_set},
    background={"transporter_orthologs": universe},
    cluster_metadata={"transporter_orthologs": {}},
)
term2gene = to_dataframe(genes_by_ontology(
    ontology="cyanorak_role", organism="MED4", level=1,
    min_gene_set_size=0, max_gene_set_size=None, limit=None,
))
result = fisher_ora(inputs, term2gene)
```

To test each group separately, build one gene set per `group_id` from the same
rows — the background stays the organism universe for every set.

---

## 7. Custom gene list (simplest form)

```python
gene_sets = {"my_genes": ["PMM0263", "PMM0628", "PMM0392"]}
inputs = EnrichmentInputs(
    organism_name="MED4",
    gene_sets=gene_sets,
    background={name: universe for name in gene_sets},   # dict, one list per set
    cluster_metadata={name: {} for name in gene_sets},
)
result = fisher_ora(inputs, term2gene, min_gene_set_size=2)
```

The background must be the pool the genes were drawn from (section 9). Any DataFrame
with `term_id`, `term_name`, `locus_tag` columns works as `term2gene` — a
clusterProfiler TERM2GENE frame, a CSV, or a hand-built frame with no KG at all
(`--scenario custom` in the example script ends with one).

**Accessors on a bare `fisher_ora` result.** `explain`, `overlap_genes`,
`background_genes`, `to_compare_cluster_frame`, `cluster_context`,
`why_skipped` and `missing_terms` all work. `generate_summary()` and
`to_envelope()` do not — they read the DE / cluster metadata that the two
wrappers merge in (`experiment_id`, `direction`, `omics_type` columns,
`result.params`) and raise `KeyError` without it. Use `result.results`
directly; the envelope is for wrapper output.

---

## 8. BRITE, InterPro, TCDB — scope the universe

**BRITE** is 12 independent trees; `enzymes` alone has 2,114 terms (1,831 at
level 3) against 188 for `transporters`, so an unscoped run is an enzyme run.
Always pass `tree=` (`list_filter_values("brite_tree")` lists them):

```python
term2gene = to_dataframe(genes_by_ontology(
    ontology="brite", organism="MED4", level=1, tree="transporters",
    min_gene_set_size=0, max_gene_set_size=None, limit=None,
))
```
or `pathway_enrichment(..., ontology="brite", tree="transporters", level=1)`.

**InterPro** has 8 entry types that size very differently at the same level;
`interpro_type=` is **required** on both enrichment tools for
`ontology="interpro"` (raises otherwise). See section 11 and
`docs://analysis/annotation_evidence`.

**TCDB** TERM2GENE is built from every `Gene_has_tcdb_family` edge (recall
semantics). Do not pre-filter membership by `tcdb_evidence_score`, by
`annotation_types`, or to deepest attachments: the same rule must define
numerator and denominator. Trust filters (section 11) are the sanctioned way to narrow
— they move gene set and background together. What an enriched family
*transports* is a chemistry question — `docs://analysis/metabolites`.

---

## 9. Choosing a background

The background is the denominator: which genes *could* have been selected by
the process that produced the gene set? It matters more than the ontology.

| Mode | When | How |
|---|---|---|
| `table_scope` (DE default) | Gene sets came from a DE table. Each experiment quantifies a subset of the genome (`distinct_gene_count` on `list_experiments`); unquantified genes cannot be DE and would inflate `N`. | `de_enrichment_inputs` sets it per gene set; `pathway_enrichment(background="table_scope")`. |
| `cluster_union` (cluster default) | Gene sets are clusters of one analysis; the universe is what was clustered. | `cluster_enrichment_inputs`; `cluster_enrichment(background="cluster_union")`. |
| `organism` | Genome-wide partitions: ortholog groups, sequence features, curated lists. | `background="organism"` on either wrapper, or the `run_cypher` one-liner in section 6 for the primitives. |
| explicit list | You know the candidate pool. | `background=[...]` on either wrapper (shared across sets), or a per-set dict on `EnrichmentInputs`. |

Backgrounds are per gene set, so `N` differs between sets and
`fold_enrichment` is not comparable across experiments. That is intended.

---

## 10. Informative-only filtering

`pathway_enrichment`, `cluster_enrichment` and `ontology_landscape` default to
`informative_only=True`; `search_ontology`, `genes_by_ontology` and
`gene_ontology_terms` default to `False`. The filter drops terms flagged
`is_uninformative='true'` in the KG at the term-match stage of the TERM2GENE
query — gene sets and backgrounds are untouched; only the set of (gene set,
term) pairs tested shrinks. Because BH is per gene set, `p_adjust` is only
comparable between runs with the same setting; raw `pvalue` is unaffected.

**What the flag actually covers (live KG).** GO roots (`go:0008150`,
`go:0003674`, `go:0005575`) and other root / catch-all terms are flagged. KEGG
is flagged at two levels: KO catch-alls (`K…; uncharacterized protein`, 212 of
4,644 KOs) and the global / overview pathway maps — `kegg.pathway:ko01100`
"Metabolic pathways" (519 of 1,973 MED4 genes, 26%), `ko01110`, `ko01120` and
the `ko012xx` block, 11 of the 13 parentless pathway nodes — so a `level=2`
KEGG run under `informative_only=True` has those rows removed. `ko01310`
Nitrogen cycle and `ko01320` Sulfur cycle are deliberately kept (narrow,
class-bearing subsets). Category / subcategory nodes are never flagged; they
are not `level=2` targets. The `map…`-style id quoted in older docs never
existed in the KG.

`is_informative` is on every result row in either mode, so one
`informative_only=False` run gives both views. `result.params["informative_only"]`
records the setting; for locked baselines run with `False` and post-filter.

---

## 11. Trust filters

Both enrichment tools accept the annotation-trust filters from
`docs://analysis/annotation_evidence`: `sources`, `evidence`, `max_tier`,
`min_evidence_score` (the only numeric cutoff), `call_class` (MEROPS) and
`interpro_type` (InterPro; required there). They are `None` by default — no
filter unless you set one.

The filters shape the TERM2GENE mapping **and** the background identically:
both come from the same gene→term match, so a gene whose only edge to a term
fails the filter is absent from the term's members in numerator and
denominator alike. The envelope echoes this as `filters_applied` (what you
set), `trust_axes` (what this ontology can be filtered on),
`background_filtered` (`True` when an edge-level filter was set; a facet like
`interpro_type` or `tree` selects terms and does not count) and `interpro_type`.

```python
result = pathway_enrichment(
    organism="MED4", experiment_ids=experiment_ids,
    ontology="tcdb", level=2, evidence=["homology"], min_evidence_score=0.6,
)
result.to_envelope(summary=True)["background_filtered"]   # True
```

`evidence_score_signals` (what the composite is made of) is not on the
enrichment envelope — read it from a `genes_by_ontology` call with the same
filters. `call_class=["peptidase"]` is the usual MEROPS choice; omitting it
folds `nonpeptidase_homolog` genes into every gene set.

---

## 12. Interpretation

- **`signed_score`** = `sign × −log10(p_adjust)` (up +, down −) is a plotting
  scalar. When a term is significant in both directions of the same experiment
  the collapsed row hides one of them — read both before trusting the sign.
- **Catch-all terms.** Cyanorak `R.2` "Conserved hypothetical proteins" and
  `D.1` "Adaptation / acclimation" enrich in many treatments because they are
  large; `fold_enrichment` penalises large `M` better than `p_adjust` does.
- **FDR is per gene set.** BH controls the false-discovery rate within one
  experiment × timepoint × direction. The same term significant across many
  experiments (`by_experiment`) is replication, not a correction artefact; for
  a run-wide correction collect `pvalue` and apply BH yourself.
- **Timepoints do not align across experiments** (`T0` ≠ `T0`), so there is no
  `by_timepoint` rollup. Group by `treatment_type`, or use
  `differential_expression_by_ortholog` for cross-organism comparison.
- **GO depth is best-effort.** GO is a DAG; `level` is the min path from root.
  Terms whose depth is ambiguous carry the one-state KG string flag
  `level_is_best_effort='true'` (absent otherwise), surfaced as
  `level_is_best_effort=True` / `None` on verbose `genes_by_ontology` rows;
  `ontology_landscape` summarises it as `best_effort_share`. Prefer
  `cyanorak_role`, `tigr_role`, `cog_category` or `kegg` when exact level
  semantics matter.

---

## 13. Gotchas

- **`min/max_gene_set_size` scope differs by tool.** `ontology_landscape`
  filters on genome-wide term size (to rank levels); `fisher_ora` and the
  wrappers filter per gene set on **M**, the term's members inside that set's
  background. Under `table_scope` a term can pass in one set and be dropped in
  another. When you call `genes_by_ontology` yourself for TERM2GENE, disable
  its own size filter (`min_gene_set_size=0, max_gene_set_size=None`) so the
  filter is applied once.
- **`limit`.** `genes_by_ontology` defaults to a paged response; pass
  `limit=None` for a complete TERM2GENE frame.
- **Null timepoints become the gene set `"NA"`** (`"<exp>|NA|up"`), not dropped.
- **`clusters_skipped` shapes differ.** Pathway kind: `{cluster, reason}` with
  `empty_background` / `empty_gene_set` / `no_pathways_in_size_range`. Cluster
  kind: `{cluster_id, cluster_name, member_count, reason}` with
  `below min_cluster_size (n)` / `above max_cluster_size (n)`. `result.why_skipped(name)`
  reads either.
- **A gene set with no rows** is not an error — check `clusters_skipped` and
  `params["n_clusters_tested"]`.

---

## 14. Divergences from clusterProfiler

| Difference | This implementation | clusterProfiler |
|---|---|---|
| Background | Per gene set (`table_scope` / `cluster_union` / organism / explicit) | One user-supplied universe |
| Ontology selection | `ontology_landscape` coverage ranking | Manual |
| DAG-level honesty | `level_is_best_effort` on GO terms | Levels used as-is |
| `min_gene_set_size` default | 5 (≈2k-gene genomes) | 10 |
| q-value | Not computed — BH only | Optional Storey q |
| BH scope | Per gene set | Per cluster in compareCluster |

`gene_ratio`, `bg_ratio`, `rich_factor`, `fold_enrichment`, `count`, `bg_count`
are clusterProfiler-compatible; `cluster` ↔ `Cluster`, `term_id` / `term_name`
↔ `ID` / `Description`. `to_compare_cluster_frame()` renames them.

---

## 15. Field reference

### Fisher 2×2 per (gene set, term)

|                          | In term     | Not in term     | Total   |
|--------------------------|-------------|-----------------|---------|
| **Gene set**             | `a = k`     | `b = n − k`     | `n`     |
| **Background, not in set** | `c = M − k` | `d = N − n − c` | `N − n` |
| **Background total**     | `M`         | `N − M`         | `N`     |

`k = count`, `n` = gene-set size within the background, `M = bg_count`,
`N` = background size. One-sided (`alternative="greater"`).

### Result rows (`result.results`, one per gene set × term)

| Field | clusterProfiler | Meaning |
|---|---|---|
| `cluster` | `Cluster` | Gene-set name (`"{experiment_id}|{timepoint}|{direction}"` for DE; `cluster_name` for clusters; your key otherwise) |
| `term_id`, `term_name` | `ID`, `Description` | Term |
| `level`, `is_informative`, `tree`, `tree_code`, `interpro_type` | — | Term context passed through from `genes_by_ontology` (`tree*` BRITE-only, `interpro_type` InterPro-only) |
| `gene_name`, `product`, `gene_category` | — | Passed through from the term's **first** gene in `term2gene` — term-level placeholders, not the overlap; use `overlap_genes()` for genes |
| `count` | `Count` | `k` |
| `bg_count` | — | `M` |
| `gene_ratio`, `gene_ratio_numeric` | `GeneRatio` | `"k/n"`, `k/n` |
| `bg_ratio`, `bg_ratio_numeric` | `BgRatio` | `"M/N"`, `M/N` |
| `rich_factor` | `RichFactor` | `k/M` |
| `fold_enrichment` | `FoldEnrichment` | `(k/n)/(M/N)` |
| `pvalue`, `p_adjust` | `pvalue`, `p.adjust` | Fisher p; BH within the gene set |
| `signed_score` | — | Pathway kind only: `sign × −log10(p_adjust)` |
| `experiment_id`, `name`, `timepoint`, `timepoint_hours`, `timepoint_order`, `direction`, `omics_type`, `table_scope`, `treatment_type`, `background_factors`, `is_time_course`, `growth_phase` | — | Pathway kind: `cluster_metadata` merged per row |
| `cluster_id`, `cluster_name`, `member_count`, `cluster_functional_description`, ... | — | Cluster kind: `cluster_metadata` merged per row |

Edge-level trust columns (`evidence`, `sources`, ...) are deliberately **not**
passed through — they describe one gene's annotation, not the term.

### `generate_summary()` / `to_envelope()` keys

Both kinds: `organism_name`, `ontology`, `level`, `total_matching` (rows pageable
under the active `include_nonsignificant` filter — see below), `n_significant`
(`p_adjust < pvalue_cutoff`, always the full tested-set count), `not_found`,
`not_matched`, `term_validation` (`{not_found, wrong_ontology, wrong_level,
filtered_out}` for `term_ids`), `clusters_skipped`, `enrichment_params` (=
`result.params`).

Pathway kind adds `no_expression`, `by_experiment[]` (`n_tests`, `n_significant`,
`n_clusters` + experiment metadata, sorted desc by `n_significant`), `by_direction[]`,
`by_omics_type[]`, `cluster_summary` (`n_clusters`, min/median/max of `n_tests`,
`n_significant`, `universe_size`), `top_clusters_by_min_padj[]` (5),
`top_pathways_by_padj[]` (ranked by `p_adjust` ascending). A detail call
(`summary=False`) caps `by_experiment` and `top_pathways_by_padj` to their first
10 entries, adding a sparse `<key>_truncated: true` sibling key when a list is
actually capped; `summary=True` carries each list in full.

Cluster kind adds `analysis_id`, `analysis_name`, `cluster_method`,
`cluster_type`, `omics_type`, `treatment_type`, `background_factors`,
`growth_phases`, `experiment_ids`, `tree`, `by_cluster[]` (`cluster_id`,
`cluster_name`, `member_count`, `significant_terms`), `by_term[]` (top 10 terms
by number of gene sets where significant), `clusters_tested`.

`to_envelope(summary=False, limit=None, offset=0)` adds the trust block
(`filters_applied`, `trust_axes`, `background_filtered`, `interpro_type`) and
pagination (`results`, `returned`, `truncated`, `offset`). `results` is sorted by
`p_adjust`, then `cluster`, then `term_id`, so paging recovers positions 11+ of
`top_pathways_by_padj`.

`include_nonsignificant` (an `EnrichmentResult.params` key, not a `to_envelope`
argument — set it via the `pathway_enrichment`/`cluster_enrichment` call) gates
a `p_adjust < pvalue_cutoff` filter applied to the sorted frame, before the
`offset`/`limit` slice. The MCP tools default `include_nonsignificant=False` +
`limit=25`, so the default response carries only significant rows; the Python
package default is `include_nonsignificant=True` (the full ranked list), so
scripts calling `pathway_enrichment`/`cluster_enrichment` directly are
unaffected unless they pass the flag explicitly.

`total_matching` counts the rows actually pageable under this filter: the
full tested-set size when `include_nonsignificant=True`, or exactly
`n_significant` when False — so an empty `results` page always implies
`total_matching == 0` (the repo-wide empty-layer invariant: a well-formed
empty result never pairs a zero page with a nonzero total). `n_significant`
itself, and every other `generate_summary()` aggregate (`by_experiment`,
`by_cluster`, `clusters_skipped`, `cluster_summary`, ...), are unaffected by
the flag and always reflect the full tested set — the all-tested count is
still recoverable there even when `total_matching` has been narrowed (e.g.
summing `by_experiment[].n_tests` for pathway kind). A cluster with zero
significant rows under the default contributes no rows to `results`, but
still appears in `by_experiment` / `by_cluster` with
`n_significant`/`significant_terms == 0` — it is not the same as
`clusters_skipped` (that bucket is for clusters that produced no Fisher
tests at all).

### `result.params` (wrapper output only)

`organism`, `ontology`, `level`, `term_ids`, `tree`, `informative_only`,
`min_gene_set_size`, `max_gene_set_size`, `pvalue_cutoff`,
`include_nonsignificant`, `background_mode`,
`n_clusters_input`, `n_clusters_tested`, `n_clusters_skipped`,
`term2gene_row_count`, `n_unique_terms`, `multitest_method` (`fdr_bh`), plus the
trust block; pathway kind also `experiment_ids`, `direction`, `significant_only`,
`timepoint_filter`, `growth_phases`; cluster kind `analysis_id`,
`min_cluster_size`, `max_cluster_size`. Save it with the frame — it is the
reproducibility record.

### `EnrichmentResult` attributes and accessors

`results` (DataFrame), `inputs` (`EnrichmentInputs`), `term2gene`, `params`,
`kind` (`"pathway"` / `"cluster"`), `clusters_skipped`, `term_validation`.

- `explain(cluster, term_id) -> EnrichmentExplanation` — narrative + Fisher
  numbers + gene refs; `_repr_markdown_()` renders in Jupyter.
- `overlap_genes(cluster, term_id)` / `background_genes(cluster, term_id)` —
  `list[GeneRef]` (`locus_tag`, `gene_name`, `product`, DE stats when the
  inputs carry `gene_stats`).
- `cluster_context(cluster)` — metadata + `n_tests` + `n_significant`.
- `why_skipped(cluster)` — reason string or `None`.
- `to_compare_cluster_frame()` — `Cluster, ID, Description, GeneRatio, BgRatio,
  pvalue, p.adjust, geneID` (`/`-joined overlap).
- `missing_terms()` — the `term_validation` buckets.
- `generate_summary()`, `to_envelope(...)` — see above; wrapper output only.

### `term2gene` columns

`term_id`, `term_name`, `locus_tag` are required (missing → `ValueError`).
`gene_name` and `product` feed `GeneRef` (None if absent). Every other column
is passed through to result rows from the term's first gene, except the
edge-owned trust / native-detail columns, which are dropped.

---

## 16. References

- yulab-smu biomedical knowledge mining book:
  https://yulab-smu.top/biomedical-knowledge-mining-book/
- Xu, S. et al. Using clusterProfiler to characterize multiomics data.
  *Nat Protoc* **19**, 3292–3320 (2024). doi:10.1038/s41596-024-01020-z
- Yu, G. et al. clusterProfiler: an R Package for Comparing Biological Themes
  Among Gene Clusters. *OMICS* **16**, 284–287 (2012).
