# KG-side frictions (reframed) — conversation seed for unresolved items

**Date:** 2026-05-01
**Supersedes (for unresolved items only):** the unresolved entries in
`2026-04-30-kg-side-requirements-and-questions.md`. The shipped items there
(KG-1 *Alternative locus ID*, KG-2 *N/A* normalization, KG-7a AA sequences)
are not revisited here — they were appropriately solution-shaped because the
problem and resolution were both contained.
**Audience:** KG team conversation.

## Why this doc exists

The 2026-04-30 doc framed each gap as a **proposed solution** (add property X,
filter string Y, re-run pipeline Z). The KG team's triage at
`second_multiomics/plans/2026-04-30-explorer-asks-triage.md` showed why this
framing under-served the conversation:

- **KG-3** asked for "re-run pipelines on TX50_RS genes". The KG team's reply:
  the underlying problem is upstream — those genes were never in any
  source study's universe; re-running clustering can't fix that. The
  explorer's actual underlying need is to **distinguish "no data" from "out of
  upstream scope"**. The proposed fix-shape never addressed it; KG-5's
  separate derivation does, by accident.
- **KG-4** asked for "add `is_uninformative` flag". Pre-decided binary
  granularity, node location, vocabulary scope. KG team came back with three
  alternative patterns (KG-side flag, explorer-side list, hybrid YAML) — none
  matchable to the original ask without retranslating.
- **KG-5** and **KG-6** had similar shape issues — pre-baked schema additions
  rather than friction descriptions.

This doc reframes the 4 unresolved items + 2 deferred-pending-demand items
in a problem-first shape:

- **Friction** — what the explorer/LLM/analyst can't do
- **Concrete instance** — pointer to where it bit
- **Desired affordance** — what we want to be able to do
- **Resolution space (open)** — multiple options not pre-decided; KG team
  picks / proposes alternates / pushes back
- **Constraints we know about** — to inform the choice
- **What we're explicitly NOT asking for** — anti-scope to keep the
  conversation tight

Verification facts (Cypher + counts) in the prior doc are still authoritative
where they apply.

---

## F-FRICTION-1 (was KG-4) — Term-level content informativeness is invisible

### Friction

Consumers (analyst or LLM) can read **which ontology source** has a term for
a gene (`Gene.annotation_types: list[str]`) but cannot read **whether the
term content is informative or a catch-all stub** without fetching the term
itself and reading its name. The source-level signal is not a reliable
proxy: every source carries a small tail of informative terms and a long
tail of catch-all "this is hypothetical" terms.

### Concrete instance

Trigger analysis `2026-04-29-1025-axenic_up_hypotheticals_med4` step 2,
F2 entry. The LLM partitioned the 116 candidate genes into `informative` /
`hypclass-only` / `no-ontology` using `annotation_types` (a list of source
names) as the discriminator. Of the 309 candidate-set ontology rows, the
COG / Cyanorak / TIGR sources mostly carry catch-alls (e.g. COG "Function
unknown" on 83 genes, TIGR "Hypothetical proteins / Conserved" on 84,
Cyanorak "Other > Conserved hypothetical proteins" on 57) but **also carry
a small tail of informative terms in this very candidate set** — COG
"Coenzyme transport and metabolism" (2 genes), Cyanorak "Cellular
processes > Adaptation/acclimation > Phosphorus / Iron" (~7 genes),
Cyanorak "Cell envelope > Surface structures" (1), TIGR "Transcription /
Other" (1). The source-level partition mis-classified ~16 of 116 genes.
The retraction is in the analysis's notebook, decision section,
`2026-04-29 — Retract the source-level …` entry.

### Desired affordance

The explorer should be able to answer, per (gene, term) pair: **is this
term content-bearing, or is it a catch-all stub?** With that signal it
can: (a) surface a per-gene `informative_annotation_types` field on
`gene_overview`, (b) roll up an `informativeness_breakdown` envelope over
a candidate set, (c) filter `gene_ontology_terms` results to
content-bearing terms.

### Resolution space (open)

Several patterns could give the explorer this signal:

- **(a) KG-side flag.** Property on each ontology term node:
  `is_uninformative: bool` or `informativeness_class: str`. Single source
  of truth; consumable by Cypher (e.g. ontology-landscape, enrichment).
  Cost: schema decision (binary vs enum), curation, post-import wiring.
- **(b) Explorer-side static list.** YAML/JSON in
  `multiomics_explorer/`, applied at query time on the explorer side.
  Cheapest to ship; doesn't require a KG rebuild for vocabulary changes.
  Cost: scattered if multiple consumers need it; drifts from KG.
- **(c) Hybrid.** Curated YAML in one repo (probably
  `multiomics_kg/config/uninformative_terms.yaml`), referenced from both
  sides. KG applies it at post-import to set node flags; explorer can
  also import the YAML directly for non-KG-call paths (e.g. test
  fixtures).
- **(d) Do nothing structural; document the convention.** Every consumer
  knows the catch-all term names; we maintain them inline in research
  scripts.
- **(e) Different signal entirely.** Maybe the right axis isn't
  "informative vs catch-all" but something the KG side knows that we
  don't — e.g. a term's `gene_count` across the whole organism (terms
  that hit > N% of all genes are catch-all-by-shape).

The KG team's triage recommended (c) hybrid. We're open. The choice
should fall out of the catch-all *vocabulary* discussion, not the
*mechanism* discussion.

### Constraints / what we know

- The catch-all vocabulary is small and stable: ~10–30 term names across
  all ontology sources. Examples (from F2 + KG team's proposal):
  COG "Function unknown" (S category), TIGR "Hypothetical proteins /
  Conserved", TIGR "Not Found", Cyanorak "Other > Conserved hypothetical
  proteins", Cyanorak "Other > Conserved hypothetical domains", Pfam
  "Domain of unknown function (DUF*)", Pfam "Protein of unknown
  function (UPF*)", GO root terms (GO:0003674 / GO:0005575 / GO:0008150).
- The set is **term-vocabulary, not strain-specific** — same catch-alls
  across all organisms.
- Pfam DUF/UPF is genuinely contested — see "What we're NOT asking" below.

### What we're explicitly NOT asking for

- **A graph-traversal informativeness score** (e.g. "how specific is this
  GO term in the DAG"). That's a different problem; defer.
- **Per-experiment informativeness** ("this term is informative for
  N-stress analyses but not phage analyses"). Out of scope.
- **A binary verdict on Pfam DUF/UPF.** These are contested:
  - Argument for *uninformative*: name explicitly says "unknown function".
  - Argument for *informative*: a recognized structural domain *is* a
    signal — distinct from "no annotation at all". The trigger analysis F1
    specifically called out DUF hits as a candidate signal for the no-
    ontology candidate subset (PMM0958 = DUF1830, PMM0684 = DUF1651).
  - **Recommend leaving DUF/UPF UN-flagged in (a)/(b)/(c).** Treat as
    informative-shaped. If a consumer wants to filter them, they filter
    them. The KG-level flag should mark only the no-content stubs.

### Joint resolution

**Decision: Path C (both axes), decomposed into three KG-side ships.**

1. **Term-node flag (data primitive).** Add `is_uninformative: bool` on
   ontology term nodes (`BiologicalProcess`, `MolecularFunction`,
   `CellularComponent`, `CogFunctionalCategory`, `CyanorakRole`, `TigrRole`,
   `Pfam`). Set in post-import from a hardcoded YAML at
   `multiomics_kg/config/uninformative_terms.yaml`. Vocabulary scope: the
   ~10–30 catch-all terms enumerated under "Constraints" above (COG "Function
   unknown" / S category, TIGR "Hypothetical proteins / Conserved", TIGR "Not
   Found", Cyanorak "Other > Conserved hypothetical proteins" / "Other >
   Conserved hypothetical domains", GO root terms GO:0003674 / GO:0005575 /
   GO:0008150). **Pfam DUF/UPF stay UN-flagged** per the anti-scope — a
   recognized structural domain is treated as informative.

2. **Refine `Gene.annotation_quality` (numeric 0–3) to be informativeness-aware.**
   Existing rule counts any structured-annotation hit toward the score; updated
   rule counts only terms where `is_uninformative IS NULL OR = false`.
   Preserves the existing 0–3 shape and consumers; stops inflating on
   catch-all hits.

3. **Add `Gene.annotation_state` (categorical enum) for partition-shaped use.**
   Values: `{no_evidence, hypothetical_only, partial, well_annotated}`.
   Explicitly carves out the hypclass-only state that the F1 trigger analysis
   needed and that the numeric score collapses indistinguishably with
   weakly-annotated real-product genes.

Companion change: the per-gene rollup `Gene.annotation_types` is rebuilt
informativeness-aware (tightened in place, or paralleled with
`informative_annotation_types` — implementation choice; raw edge existence
remains recoverable via `EXISTS { (g)-[:edge_type]->() }` either way).

Vocabulary YAML schema, exact post-import Cypher, and final field naming are
deferred to a KG-side design doc opened when implementation starts.

### Explorer review

The 3-primitive split is the right shape. Two specifics on the individual ships:

**Ships 1 (`term.is_uninformative`) and 3 (`Gene.annotation_state`) are the
load-bearing primitives.** Term-node flag gives `gene_ontology_terms` a clean
filter; `annotation_state` enum directly carries the F1 trigger partition
(`hypothetical_only` is the bucket the trigger analysis tried to build).
DUF/UPF stay un-flagged per the joint anti-scope. Both ships are accepted
as proposed.

**Ship 2 (`annotation_quality` refinement) — accept, but treat as a
breaking-baseline event.** Refining catch-all-blind → catch-all-aware is a
real bug fix (today's score inflates on COG "Function unknown" /
TIGR "Hypothetical proteins / Conserved" hits). But it WILL shift the
candidate sets of existing filters — e.g. the trigger analysis's
`annotation_quality ≤ 1` "weakly annotated" filter grows after the fix.
Coordinated request:

- Land all 4 F1 ships in one KG release so consumers calibrate once, not
  iteratively.
- Document the new scoring rule in `gene_overview` about-content + the
  `gene_overview.annotation_quality` field description.
- Expect explorer-side regression baseline rebaseline as part of the
  release acceptance (in addition to fixture drift from other 2026-05-01
  changes).
- Flag the semantic change in the KG release notes and CLAUDE.md MCP
  tools table.

**Ship 4 (`annotation_types` rebuild) — please pick the parallel-field
option, not tighten-in-place.** Add `Gene.informative_annotation_types:
list[str]` next to the existing `Gene.annotation_types`. Reasons:

- Pass A's F-AUDIT-2 layer 1 (just shipped 2026-04-30) clarified
  `annotation_types` description as "presence-by-source — does NOT
  indicate content informativeness". Tightening the field's meaning to be
  informativeness-aware days later would invalidate that fix.
- Two surfaces are genuinely useful at different times: source presence
  ("does any kind of content exist?") vs informative-source presence
  ("does *informative* content exist?"). Different routing decisions hang
  off each.
- Additive change is cheaper for consumers than breaking change.

### KG response

All four asks accepted as proposed.

- **Ship 4 → parallel field.** Will add `Gene.informative_annotation_types:
  list[str]` alongside the existing `Gene.annotation_types`. Existing field
  semantics preserved (presence-by-source, ontology-type granularity); new
  field counts only sources contributing at least one term where
  `is_uninformative IS NULL OR = false`. Cross-reference between the two
  fields in the post-import Cypher comment block + the implementation spec.
- **Bundled F1 release.** All four ships (term-flag, refined
  `annotation_quality`, new `annotation_state`, parallel
  `informative_annotation_types`) ship in a single KG release. KG-side
  design doc will plan as one work unit; release notes will call out the
  semantic shift in `annotation_quality` (catch-all-blind →
  catch-all-aware) explicitly, with a worked before/after example.
- **Doc surfaces.** New scoring rule in the `gene_overview` about-content
  + the `annotation_quality` field description in `kg_schema` output +
  CLAUDE.md "Gene properties" subsection updated. KG release notes flag the
  shift on the MCP-tools table line.
- **Baseline rebaseline.** Expected and OK as part of release acceptance.

---

## F-FRICTION-2 (was KG-5) — Empty results conflate "no hit" with "out of scope"

### Friction

When a per-gene tool (`gene_homologs`, `gene_clusters_by_gene`,
`gene_ontology_terms`, `gene_derived_metrics`) returns zero rows for a gene,
the consumer can't tell:

- (a) the upstream pipeline ran on this gene and found no result
- (b) the upstream pipeline never had data on this gene (out of scope)
- (c) the gene doesn't exist in the KG (already handled via `not_found`)

Cases (a) and (b) get conflated under `no_groups` / `not_matched` / empty
results. The consumer is left with an ambiguous "the KG returned nothing"
that could mean either.

### Concrete instance

Trigger analysis F3. `TX50_RS09500` and `TX50_RS09520` returned empty
across `gene_homologs.no_groups`, `gene_clusters_by_gene.not_matched`, and
`gene_ontology_terms` zero rows. The genes exist in the KG. The KG team's
triage clarified the actual reason: cyanorak doesn't curate them; the
clustering-source studies didn't measure them; eggNOG runs on them but
returns no hit. From the API surface, the "we ran and found nothing"
case (eggNOG) was indistinguishable from the "we never ran" case (cyanorak,
clustering).

### Desired affordance

When zero results come back from a per-gene tool, the consumer should be
able to read **why**: at minimum, "in scope but no hit" vs "out of scope".
Concrete shape: per-row or per-envelope `out_of_scope: list[pipeline_name]`
listing pipelines that didn't process this gene at all. With it: (a) the
LLM stops over-interpreting empty results as "nothing biologically there",
(b) downstream analyses can characterize floor cases honestly, (c)
`gene_overview` can surface a per-gene "data-availability mask" cleanly.

### Resolution space (open)

- **(a) KG-side derivation.** Post-import Cypher derives
  `Gene.processed_by_pipelines: list[str]` from existing edges/properties
  (KG team's proposal). Explorer reads it; surfaces `out_of_pipeline_scope`
  envelopes from it.
- **(b) KG-side per-pipeline edge.** Heavier:
  `(Gene)-[:processed_by {version, run_date}]->(Pipeline)`. Useful if
  pipeline-version metadata ever becomes load-bearing. Premature today.
- **(c) Explorer-side heuristic.** Map locus-tag prefix to source-set
  ("TX50_RS → not in cyanorak"). Fragile; only catches one observed
  instance.
- **(d) Convention + documentation.** Document that empty per-gene
  results are ambiguous; consumers infer scope from organism-level
  context. No structural change.
- **(e) No surface at all.** Treat floor cases as floor cases; the LLM
  learns to say "no data on this gene, reason unknown".

KG team's triage recommended (a). We agree it's the right shape;
question is what's in the list — see joint resolution below for the
reframed answer (4 sources, not 9 pipelines).

### Constraints / what we know

- Pipeline set is small and stable. KG team proposed 9: `cyanorak_curation`,
  `eggnog_v5`, `cyanorak_orthogrouping`, `kegg_ko_assignment`,
  `pfam_assignment`, `go_assignment`, `cog_assignment`,
  `tigr_role_assignment`, `cyanorak_role_assignment`.
- Coverage per (gene, pipeline) is binary today: in-scope or not.
- The friction recurs whenever gene scope and pipeline scope diverge.
  With the new heterotroph organisms (Pseudomonas, Meiothermus,
  Marinobacter MarRef, additional Alteromonas strains) added in the
  2026-05-01 KG rebuild, more pipelines now have partial coverage —
  the friction will be more common, not less.

### What we're explicitly NOT asking for

- **Per-pipeline run version / date metadata.** Premature. No current
  analysis gates on it.
- **A quality / score signal per (gene, pipeline).** Just presence /
  absence.
- **An upstream explanation** ("why doesn't cyanorak cover this gene").
  Beyond the explorer's responsibility.
- **Distinguishing "ran but failed" from "ran but found nothing"** within
  a single pipeline. Both are "in scope, no hit" and that's enough.

### Joint resolution

**Decision: collapse the 9-pipeline framing to 4 sources, surface a `DataSource`
node table generated from `config/gene_annotations_config.yaml`, and carry
per-gene presence as a `Gene.contributing_sources: list[str]` property. No
materialized Gene→DataSource edges.**

Sources (extensible — start with 4, grow as the KG grows):

- **`ncbi`** — gene-level. Every Gene node has it by definition (no Gene
  exists without an NCBI GFF row).
- **`cyanorak`** — organism-restricted (Pro/Syn only); within in-scope
  organisms, gene-level (individual loci can be missing).
- **`uniprot`** — gene-level (joins via `protein_id` / WP_ accession).
- **`eggnog`** — gene-level (per-protein query; can return no hit even when
  attempted).

`DataSource` node shape:

```
(:DataSource {
  id: 'eggnog',                      # join key, matches values in Gene.contributing_sources
  name: 'EggNOG-mapper',
  description: 'Functional annotations via orthology to eggNOG OGs',
  version: '5.0.2',                  # optional v1; populated where derivable
  scope: 'gene_level',               # 'gene_level' | 'organism_restricted'
  applies_to_organisms: [],          # populated only for organism_restricted (cyanorak: Pro/Syn)
  info_types: ['cog_category', 'kegg_ko', 'go_terms', 'pfam_ids',
               'eggnog_ogs', 'function_description', ...]
})
```

`info_types` is **auto-generated** by walking `config/gene_annotations_config.yaml`
fields and inverting source → field-name mapping. The YAML grows two new
per-source metadata keys (`scope`, `applies_to_organisms`); everything else
is derived. No drift between the merge config and the surfaced metadata.

Gene-side: `Gene.contributing_sources: list[str]` computed in
`build_gene_annotations.py` from the existing `*_source` track fields,
`[prefix]` tags in `alternate_functional_descriptions`, and presence of
source-tagged fields (e.g., `eggnog_ogs` non-null → eggnog ran on this gene).

Explorer reads `Gene.contributing_sources`, joins to `DataSource.info_types`
to interpret what each source contributes, and surfaces the
`out_of_pipeline_scope` envelope honestly. Empty per-gene tool results can
now be classified: source absent from `contributing_sources` → out of scope;
source present but tool returned nothing → ran but no hit.

`KGRelease` versioning node deferred until there's concrete demand; the
per-DataSource `version` field carries enough release context for v1.

Vocabulary YAML extensions, exact info_types-derivation rule, and the
DataSource adapter are deferred to the KG-side design doc.

### Explorer review

Resolution works as-is. The 4-source reframing is meaningfully better than
the 9-pipeline framing we proposed — sources carry semantics, pipelines were
verb-shaped derivations.

**Architectural note (clarified by KG team):** the 4 sources split 3+1 by
provenance. `ncbi`, `cyanorak`, `uniprot` are **downloaded** — KG pulls
records from the source; "absent" means "the source has no record for this
gene". `eggnog` is **run as a tool** (eggnog-mapper) — KG executes
per-protein; "absent" means "the tool ran and found no hit". The unified
`contributing_sources` semantic is still correct, but the meaning of
"absent" varies per source:

| Source | Provenance | "Absent from `contributing_sources`" means |
|---|---|---|
| `ncbi` | downloaded | impossible — every Gene has it by definition |
| `cyanorak` | downloaded | organism out of scope (handled by `applies_to_organisms`) OR in-scope but no record |
| `uniprot` | downloaded | no UniProt entry matched via `protein_id` |
| `eggnog` | tool run | eggnog-mapper executed on this protein and returned no hit |

**`Gene.contributing_sources` is contributed-only**, not ran/looked-up
attempted — confirmed by the proposal's derivation rule (non-null
source-tagged fields). For the explorer's user-facing question ("does this
gene have content from source X?") the contributed-only signal is what
matters; the per-source mechanism behind "absent" is upstream noise we
don't need to surface at this layer. Suggest making this explicit in
`DataSource.description` (and possibly a per-source `provenance: 'download'
| 'tool_run'` field if it earns its keep elsewhere; not strictly needed
for F2 itself).

**Coherence with existing `Gene.annotation_types` — both stay, distinguish
in docstrings.** Today `annotation_types` enumerates *ontology types*
(`cog_category`, `pfam`, `kegg`, `go_*`, `brite`, `cyanorak_role`,
`tigr_role`); the new `contributing_sources` enumerates *data sources*
(`ncbi`, `cyanorak`, `uniprot`, `eggnog`). The `DataSource.info_types`
mapping bridges them — e.g. `eggnog.info_types` includes `cog_category`,
`kegg_ko`, `pfam_ids`, `eggnog_ogs`, `function_description`. Both surfaces
stay; the explorer surfaces them as distinct routing signals (different
abstraction levels, different uses). We'll add cross-reference in the
`gene_overview` about-content + the new data-source tool's docstring. No
KG-side action needed for this — just confirming the two-surface intent
is OK.

**Floor-case interaction validates the design.** For TX50_RS09500/09520,
expected `contributing_sources = ['ncbi']` (no cyanorak record; no uniprot
match via protein_id; eggnog ran but found no hit). That's the right
surface — exact answer to "what does this gene have at all?". Validates
the model end-to-end across all 4 source provenances.

### KG response

All accepted.

- **Add `DataSource.provenance: 'download' | 'tool_run'`.** Single new
  field on a 4-row node table — earns its keep by making the meaning of
  "absent from `contributing_sources`" explicit per source, exactly as
  the review's table describes. Initial mapping:
  `ncbi=download, cyanorak=download, uniprot=download, eggnog=tool_run`.
- **Two-surface intent confirmed.** `Gene.annotation_types` (ontology-type
  presence) and `Gene.contributing_sources` (data-source presence) both
  stay; cross-reference in the new MCP data-source tool's docstring +
  `gene_overview` about-content. No KG-side action beyond docstring text.
- **Eligibility rule for "tool_run" sources.** Worth a follow-up note in
  the implementation spec: for a `tool_run` source, "absent" means the
  tool ran and returned no hit. We do not currently distinguish "tool ran
  but failed" from "tool ran and returned no hit" (per the F2 anti-scope);
  if that distinction ever becomes load-bearing, it'd be a separate
  property, not a redefinition of `contributing_sources`.

---

## F-FRICTION-3 (was KG-6) — Expression-bin analyses look like functional clusters

### Friction

Some `ClusteringAnalysis` nodes group genes by **functional similarity**
(e.g., MED4 K-means N-starvation clusters carry curated
`functional_description` like "Contains nitrogen transport genes such as
urtA and cynA"). Other ClusteringAnalysis nodes group genes by
**expression bin** (e.g., MED4 gene expression level classification,
where clusters are VEG/HEG/MEG/LEG/NEG quartile labels with no functional
content **by design**). From the consumer side, both look identical:
same node type, same fields, same shape. The "no functional content"
property of expression-bin analyses is invisible until someone reads the
cluster names and recognizes the pattern.

### Concrete instance

Trigger analysis step 5, F6 entry. Of 12 ClusteringAnalysis nodes touched
by the candidate set, the MED4 expression-level classification accounted
for 113 of 116 candidate rows but only 32 / 113 carried a curated
`functional_description`. That looked like a *curation gap* on the
busiest analysis — it's actually a *category mismatch*: VEG/HEG/MEG/LEG/NEG
clusters have no functional content to curate. The dossier surface
treated the analysis identically to K-means N-stress (which is genuinely
functional). Consumer-side filtering via `IS NOT NULL on
functional_description` happened to work but for the wrong reason —
the field is null because it's not applicable, not because it's missing.

The 2026-04-29 → 2026-05-01 KG rebuild also reshaped this terrain:
many former enrichment-style clusters became `DerivedMetric` nodes
(`enrichment_ribosome`, `enrichment_flagellar_assembly`, etc., plus
`expression_level_class` as a categorical DM). The remaining
ClusteringAnalysis set is smaller (13 today vs 12 before but with
migrations both in and out) and still mixes intents.

### Desired affordance

Consumers should be able to distinguish "this analysis is intended to
carry functional content per cluster" from "this analysis groups genes
by an expression metric and clusters carry meta-labels, not functional
descriptions". With that signal: (a) `list_clustering_analyses` filterable
by intent, (b) per-axis expectations clearer in dossier surfaces, (c)
tool docstrings can signpost different chaining patterns for different
intents.

### Resolution space (open)

- **(a) KG-side flag on ClusteringAnalysis.** `clustering_intent: str`
  enum (KG team's proposal). Cheap; explorer surfaces directly.
- **(b) Naming convention.** Suffix non-functional analyses (e.g.
  `MED4 expression-level classification (bin)`). Consumer parses the
  name. Cheap but fragile.
- **(c) Different node type.** `ExpressionBinClassification` vs
  `FunctionalCluster`. Heaviest; affects every consumer.
- **(d) Per-cluster bin-meaning text.** Populate `expression_dynamics`
  or a new field with text like "VEG = top RPKM quartile (highly
  expressed, expected to include constitutive housekeeping)". KG team
  noted this is orthogonal and already-mechanism-supported. Doesn't
  replace (a) but complements it.
- **(e) Do nothing structural.** Document the convention; consumers
  test on `name` patterns (VEG/HEG/MEG/LEG/NEG).

KG team's triage recommended (a) + (d). We agree on (a). (d) is a
paperconfig curation cost.

### Constraints / what we know

- The intent set is small. KG team proposed:
  `functional | expression_bin | condition_response | diel_phase | other`.
  Worth confirming this list covers the migration-shaped landscape after
  the 2026-05-01 rebuild.
- Intent is **per-analysis, not per-cluster** — every cluster within an
  analysis shares the intent.
- Today only one analysis (MED4 expression-level classification) is
  non-functional in the strict sense. NATL2A diel analyses (30 clusters
  uncurated) are *under-curated functional clusters*, not non-functional
  ones — different problem.
- Some former enrichment-style clusters became DMs in the latest KG
  rebuild. Whatever convention we adopt for ClusteringAnalysis intent
  should not preclude the DM family carrying analogous intent metadata
  if needed.

### What we're explicitly NOT asking for

- **Per-cluster `intent_role` flag** (one cluster is "VEG", another is
  "HEG"). The cluster `name` already encodes this. Premature.
- **Re-curation of NATL2A diel as part of this conversation.** Different
  problem — analysis-level intent flag doesn't touch the curation gap.
- **Auto-detection of intent** from analysis name or cluster shape.
  Manual paperconfig tagging is fine and probably more reliable.

### Joint resolution

**Decision: reuse the existing `cluster_type` field as the intent discriminator;
no new property, no schema change. Refine the vocabulary where a label is
ambiguous about intent.**

The friction has partially auto-resolved: the trigger instance (MED4
expression-level VEG/HEG/MEG/LEG/NEG) migrated to a `DerivedMetric` in the
2026-04-29 → 2026-05-01 KG rebuild (`metric_type: expression_level_class`,
`value_kind: categorical` in Wang 2014). The remaining ~13 ClusteringAnalysis
nodes are uniformly functional-intent (`time_course` / `diel` /
`condition_comparison`). The bin-shaped ClusteringAnalysis pattern that caused
the friction is currently unused.

Current `cluster_type` vocabulary:

- `time_course` — functional content expected per cluster (temporal axis).
- `diel` — functional content expected per cluster (diel-phase axis).
- `condition_comparison` — functional content expected per cluster
  (treatment vs control axis).
- `classification` → **rename to `expression_bin`**. The original label was
  ambiguous (could plausibly mean "functional classification" of any kind).
  `expression_bin` is unambiguous: clusters are quartile / RPKM-bin labels
  with no curated functional content per cluster by design. Migration cost
  is zero — no current paperconfig uses `classification`; only the
  paperconfig-validator vocab and skill template need updating.

Convention (documented on the KG side, surfaced in tool docstrings):

> `cluster_type=expression_bin` analyses do **not** carry per-cluster
> functional descriptions; cluster `name` is the metric label (e.g., VEG,
> HEG). All other `cluster_type` values carry per-cluster functional
> descriptions where curated.

Explorer reads `cluster_type` directly to choose dossier rendering and
chaining patterns. No derived `clustering_intent` field — the reframed
vocabulary already encodes intent.

If a future cluster type has unclear intent, the rule is: **rename or split
the `cluster_type` value rather than adding a parallel intent field**.

### Explorer review

Works as-is. The auto-resolution via DM migration plus the `cluster_type`
rename is the lightest-touch resolution and the right call.

**Reactive work the explorer will pick up when the rename lands:**

- Regenerate `list_filter_values_cluster_type` regression baseline.
- Update `list_clustering_analyses` + `gene_clusters_by_gene` about-content
  to surface the convention: `cluster_type=expression_bin` analyses don't
  carry per-cluster functional descriptions; cluster `name` is the metric
  label (e.g., VEG, HEG).
- Route differently in any dossier-style surface that anchors on cluster
  functional content — skip the "potential role from cluster" axis for
  `expression_bin` clusters. (Affects research-side analysis methodology,
  not MCP tools directly.)

No KG-side changes needed beyond the rename + the convention documentation.

**Future-ambiguity rule looks fine.** "Rename or split `cluster_type`,
don't add parallel intent" is sustainable while the universe stays small
(single-axis per analysis, manual paperconfig tagging). If the universe
ever grows mixed-axis, the rule's revisited.

### KG response

Acknowledged. KG side will land the rename
(`classification` → `expression_bin`) plus the convention text in tool
docstrings + the `paperconfig` skill template + the validator vocab. No
schema work beyond the vocab change.

---

## F-FRICTION-4 (was KG-3 follow-up) — Floor-case genes have no characterization surface

### Friction

Some genes (~14 TX50_RS-prefixed RefSeq-only loci on MED4, plus
counterparts on other organisms; plus the broader F1 17-gene MED4
no-ontology subset) have no annotation, no informative homolog group, no
cluster, no derived metric, no curated identity beyond locus_tag and
(now) AA sequence. Per-gene tools return empty across every axis. The
consumer has no surface from which to even pose a "what is this gene?"
question — even though these genes have measurable behavior (DE
significance, cross-study response profiles) that landed them in the
analysis in the first place.

### Concrete instance

Trigger analysis F1 (17 of 116 candidate genes with no ontology) +
F3 (3 of those 17 are TX50_RS-only — also no clusters, also no
homologs). PMM1898 was top-10 by log2fc (4.68, AQ=0, singleton
ortholog group); PMM1939 is similar; TX50_RS09500 / TX50_RS09520 are
the most-stripped instances. The dossier surface for these genes
reduced to identity + DE evidence + cross-study response profile only;
ontology / cluster / homolog axes all surfaced as "no data" rows.

The 2026-04-30 doc framed this as KG-3 ("re-run pipelines on TX50_RS
genes"). The KG team's reply clarified the pipelines never had data —
re-running can't change anything, because cyanorak doesn't curate these
genes and the source studies' clustering input never measured them.
The reframed friction: **the explorer surface offers nothing to
characterize these genes, even though the underlying KG carries signals
that aren't currently surfaced** (sequence, genomic context, ortholog-
mediated transfer).

### Desired affordance

For floor-case genes, the explorer should surface every signal that
*does* exist so the consumer can frame an analysis around the gene
rather than treating it as opaque. Concretely, what *is* available
today for these genes (or now, post-rebuild):

- AA sequence (KG-7a shipped — 94,694 / 97,513 genes covered)
- Genomic context (`start`, `end`, `strand`, neighboring genes)
- DE rows + cross-study response profile (already surfaced)
- Ortholog-group-mediated annotation (where any OG hit exists, even
  sibling-only ones — 9 / 14 TX50_RS have at least one)

Some are surfaced today (response profile, DE); some are not (sequence,
neighbors, ortholog-mediated transfer).

### Resolution space (open)

- **(a) MCP-side: surface what's there.** Add `Gene.sequence` to
  `gene_details` / `gene_overview`. Add genomic-neighbor lookup. No KG
  change. On the explorer roadmap as MCP-7 + Pass B.
- **(b) KG-side: ad-hoc bioinformatics layers.** Run InterPro / SignalP
  / TMHMM / AlphaFold to add annotation surfaces. KG team's triage
  showed TMHMM and SignalP are *already in KG* (Polypeptide.\* fields,
  unsurfaced — folds into MCP-7); InterPro is L+ effort with unclear
  demand; AlphaFold is wrong-tool for Neo4j storage.
- **(c) KG-side: ortholog-mediated annotation transfer.** Where a gene
  has even one OG hit, surface "best annotation among co-orthologs" as
  a fallback signal on the gene itself. Not done today; would unblock
  more than just floor cases (any sparsely-annotated gene with
  better-annotated co-orthologs benefits).
- **(d) Document the floor case explicitly.** Surface
  `data_floor: true` (or similar) on `gene_overview` with a rendered
  explanation. Sets reader expectations honestly.
- **(e) Skip — accept floor cases as floor cases.** Existing surface is
  honest; nothing more is owed. The trigger analysis dossier card for
  PMM1898 / TX50_RS09500 already renders empty axes correctly.

(a) is highest-leverage and explorer-owned. (c) is the most interesting
KG-side option but is a bigger conversation.

### Constraints / what we know

- The floor-case set is small in absolute count (~14 TX50_RS on MED4)
  but disproportionately represented in any "hypothetical upregulated"
  analysis where the no-annotation property is the inclusion filter.
- DE evidence for these genes is real and effect-sizes are large
  (PMM1898 log2fc=4.68 in the trigger experiment).
- Sequence is now in the KG (KG-7a shipped 2026-05-01).
- Ortholog-mediated transfer (option c) is most useful when the OG
  itself is well-annotated. For TX50_RS, eggNOG OGs often span
  Prochlorococcus only — sibling co-orthologs are themselves
  hypotheticals. So the value of (c) for *floor-case* genes
  specifically is bounded; for the broader sparsely-annotated
  population it's larger.

### What we're explicitly NOT asking for

- **Per-gene InterPro / AlphaFold by default.** No demand evidence yet.
- **A "characterizability score"** per gene. Premature speculation.
- **Auto-classification of floor genes into priority tiers** for
  downstream analyses. Trigger analysis F7-A3 explicitly retracted that
  pattern (the Tier 1/2/3 designation was a premature-commitment
  failure mode caught by the user mid-step).

### Joint resolution

**Decision: F4 is mostly explorer/MCP-owned (surface what the KG already has).
Concrete KG-side ships are small and contained. The big KG-side option —
ortholog-mediated annotation transfer (option c) — is deferred to its own
future spec; it's wrong-scoped under F4 because its leverage is on the
broader sparsely-annotated population, not floor cases per se.**

Audit: comparing `gene_annotations_merged.json` against the current Gene
schema, three fields are missing or absent that affect floor-case (or
broader sparsely-annotated) characterization:

| Field | Status | Decision |
|---|---|---|
| `contig` (seqid) | Missing from `gene_mapping.csv` and merged JSON; NCBI GFF has it | **Add** — required for neighbor lookups to be meaningful |
| `seed_ortholog`, `seed_ortholog_evalue` | In merged JSON; not on Gene | **Add** — gives sparsely-annotated genes a "resembles X protein at E=Y" surface even when functional fields are empty |
| Other JSON-only fields (`max_annot_lvl`, `uniprot_accession` on Gene, redundant OG fields, source provenance) | — | Skip — niche, duplicative, or covered by F-FRICTION-2's `contributing_sources` |

Concrete KG-side ships:

1. **Add `Gene.contig: str`.** Plumb the NCBI GFF `seqid` through
   `gene_mapping.csv` → `gene_annotations_merged.json` → Gene schema. Touches
   the NCBI download script, the gene-annotations passthrough config, and
   `schema_config.yaml`. Small, contained.

2. **Add `Gene.seed_ortholog: str` + `Gene.seed_ortholog_evalue: float`.**
   Already in merged JSON — surface as Gene properties. Helps the broader
   sparsely-annotated population (more than just floor cases): when
   functional fields are empty but eggNOG matched, the seed-ortholog gives
   the consumer a concrete pointer ("this gene's protein most resembles X,
   E=Y") that frames a follow-up question. Doesn't help true floor cases
   (e.g., TX50_RS where eggNOG returns no hit), but those are the absolute
   floor — every other sparsely-annotated gene benefits.

3. **Genomic neighbors as an MCP tool, not materialized edges.** With
   `contig` added, the query is trivial Cypher: same organism, same contig,
   `start` within ±N. No `(Gene)-[:NEIGHBOR_OF]->(Gene)` edge type needed.
   Lives on the explorer/MCP roadmap (MCP-7 / Pass B per the existing
   referenced direction).

What we're explicitly NOT shipping under F4:

- **No `data_floor: bool` flag** — derivable from F-FRICTION-1's
  `annotation_state` + F-FRICTION-2's `contributing_sources`. Don't add a
  parallel field.
- **No InterPro / AlphaFold layers** — confirms the existing anti-scope.
- **No ortholog-mediated annotation transfer (option c)** — deferred to its
  own future spec when the broader sparsely-annotated population becomes
  the bottleneck. The doc itself flags that floor-case OG siblings are
  usually also hypotheticals (eggNOG OGs span Prochlorococcus only), so
  (c)'s leverage on floor cases specifically is bounded; under-the-hood,
  it's a different problem with different demand.
- **No Polypeptide-derived field additions** — `transmembrane_regions`,
  `signal_peptide`, `protein_family`, `catalytic_activities`, `cazy_ids`,
  `bigg_reaction` are already on Gene. Surfacing them in dossier cards is
  explorer/MCP work.

### Explorer review

Resolution works as-is. All 3 KG-side ships are well-shaped.

**Honest framing note (no action needed).** The 3 ships primarily benefit
the **broader sparsely-annotated population** — thousands of genes with
eggnog hits but uninformative or absent functional descriptions — not the
strict F4 floor (~14 TX50_RS-style genes). The strict floor gets:

- `contig` (newly available)
- AA sequence (KG-7a, already shipped)
- Genomic neighbor lookup (newly available via `contig` + new MCP tool)
- (no `seed_ortholog` — eggnog returned no hit on these genes)

That's a small gain in absolute terms but it's what the underlying KG
has. The strict floor stays a strict floor. The big leverage is the
broader population. Framing was slightly oversold under "F4"; the ships
are still the right ones.

**Schema question to nail down:**

- **`Gene.seed_ortholog` format.** Please confirm what the field looks
  like. Eggnog's standard format is `taxid.protein_id` (e.g.,
  `1117.WP_011131234.1`); is that what lands? The explorer's tool docstring
  + about-content needs to reflect it so consumers know what they can do
  with it (e.g., look up the resembled protein in NCBI / UniProt directly,
  or pivot to its host organism's annotated context).

**Explorer-side tool-design choice (no KG dependency, raised here for
visibility):**

- **Genomic-neighbor window default.** Leaning toward `±N flanking genes
  ordered by start` (default 5 each side) as the primary parameter, with
  `±M bp` as an alternative filter. Gene-count window is gene-density-
  independent; bp window is operon-scale-natural. Open to either; will
  converge during Pass B implementation.

### KG response

All accepted; framing note acknowledged.

- **`Gene.seed_ortholog` format (confirmed empirically across organisms):**
  `<taxid>.<source_identifier>`, where `<source_identifier>` is whatever
  identifier eggnog's reference DB uses for that taxid's source — most
  commonly a locus tag, but also `<contig>_<gene_n>` for draft assemblies.
  Sample values across the current data:
  - `160488.PP_0894` — Pseudomonas putida KT2440, locus tag
  - `225937.HP15_1417` — Marinobacter HP15, locus tag (self-match: HP15 is
    in eggnog's reference)
  - `1177179.A11A3_14040` — different Marinobacter strain (cross-organism
    seed match)
  - `1122222.AXWR01000046_gene1504` — Meiothermus reference draft assembly
    (`<contig>_<gene_n>` pattern)

  The taxid prefix points at NCBI Taxonomy; the suffix is a stable identifier
  in that organism's eggnog reference. KG-side will mirror this in the
  `Gene.seed_ortholog` field description + the `gene_overview` about-content.
  Consumer can pivot to NCBI / UniProt for the resembled protein, or to the
  resembled organism's annotated context.

- **Honest-framing note acknowledged.** The F4 banner did slightly oversell
  what the strict floor gets — the bigger leverage is broader sparsely-
  annotated genes. Releases notes will land the ships under their
  population-of-effect framing rather than under "F4 floor cases", to avoid
  expectation mismatch.

- **Genomic-neighbor window default.** Explorer call; KG side has no
  preference. The Cypher pattern works equally for `±N flanking genes` or
  `±M bp` — same `MATCH (g)-[:Gene_belongs_to_organism]->(o)<-[:Gene_belongs_to_organism]-(n)
  WHERE n.contig = g.contig AND ...` structure, only the predicate differs.

---

## Deferred — no friction surfaced yet

- **InterPro** (was KG-7b). KG team estimated L+ effort. We have no
  current analysis where Pfam alone is the bottleneck. Document and
  defer.
- **AlphaFold** (was KG-7c). KG team flagged store-in-Neo4j as wrong-tool
  even if we wanted it. We have no current analysis that would consume
  structural priors. Document and defer indefinitely.
