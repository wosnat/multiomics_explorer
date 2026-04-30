# MCP usability audit — LLM-as-user perspective

**Date:** 2026-04-29
**Trigger analysis:** `multiomics_research/analyses/2026-04-29-1025-axenic_up_hypotheticals_med4/gaps_and_friction.md`
**Goal:** "Pretend you need to use the MCP — do you know how / what to use? Is it easy
to find out / select?" Audit the surface (tool catalog, signatures, field schemas,
docstrings) for clarity, interpretability, and discoverability — *not* for enforcement.

This is a findings doc, not a feature spec. Each finding describes an observed
friction point and sketches a fix shape; concrete designs are deferred to follow-on
specs (one per fix or per coherent batch).

## Method

| Lens | What it surfaces | How applied |
|---|---|---|
| **M2 — question-driven walks** | Tool selection, ordering, drill-down friction | 3 research questions, traced step-by-step |
| **M3 — Pydantic schema sample** | Field-level interpretability, naming, examples | Sampled `gene_overview`, `gene_details`, `gene_ontology_terms`, `list_experiments`, `list_publications` (5 of 30 tools, chosen because they sit on the high-traffic paths in M2) |
| **Cross-check** | Confirmation of patterns | `pathway_enrichment_b2/api_coverage.md` (already-documented friction from a separate analysis) |

### Q1 — `2026-04-29-1025-axenic_up_hypotheticals_med4`

Per-gene dossier on upregulated, weakly-annotated MED4 genes. Tools touched:
`differential_expression_by_gene`, `gene_overview`, `gene_details`,
`gene_ontology_terms`, `gene_clusters_by_gene`, `gene_homologs`,
`gene_derived_metrics`, `gene_response_profile`, `genes_by_homolog_group`.

### Q2 — `2026-04-27-1638-proteome_transcriptome_discordance`

Cross-omics paired-data discordance analysis. Tools touched:
`list_publications`, `list_experiments`, `list_derived_metrics`,
`differential_expression_by_gene`, `differential_expression_by_ortholog`,
plus Polypeptide.* sparse fields (size, signal peptide, TM regions) on `gene_details`.

### Q3 — `2026-04-20-1243-pathway_enrichment_b2`

Already documented in that analysis's `api_coverage.md`. Findings folded as
supporting evidence with cross-references to the existing b2-improvements spec.

## Findings

Severity: **HIGH** = LLM is likely to draw a wrong inference or pick a wrong tool;
**MED** = LLM has to take an extra read-and-handle pass that good docs would skip;
**LOW** = naming or discoverability rough edge.

Items already covered by `2026-04-25-b2-explorer-improvements-design.md` are
flagged inline and not re-itemized.

### F-AUDIT-1 (HIGH) — Pydantic field examples ship known-bad placeholder strings as if they were normal values

**Where:** [tools.py:838-839](../../multiomics_explorer/mcp_server/tools.py#L838-L839)

```python
gene_summary: str | None = Field(
    description="Concatenated summary text "
                "(e.g. 'dnaN :: DNA polymerase III subunit beta :: Alternative locus ID')")
function_description: str | None = Field(
    description="Curated functional description (e.g. 'Alternative locus ID')")
```

`Alternative locus ID` is the **placeholder string** flagged in F5 of the trigger
analysis — a metadata stub that pollutes `function_description` for un-curated genes
(PMM0958, PMM0689, PMM1813, …). A fresh LLM reading the schema sees that string as
the literal expected example and treats it as content-bearing. The Pydantic field
description is, in effect, training the LLM to expect this placeholder.

**Why it matters.** F5 is currently described as "the LLM mentally filters
`Alternative locus ID` as a non-description". Removing it from the schema example
removes the in-prompt normalization. Combined with boundary normalization (handled
in the user's separate "b" track) this closes the loop — the LLM neither expects
nor receives the placeholder.

**Fix shape.** Replace the example with a real, content-bearing description (e.g.
`'Required for full expression of proteins subject to ammonium repression'` from
the ntcA card). Optionally add an explicit "this field may contain placeholder
strings; consumers should test for them" caveat — though if API-boundary
normalization ships, this caveat becomes moot.

**Audit cost to fix:** XS — two-line edit in `tools.py` + regen.

---

### F-AUDIT-2 (HIGH) — `gene_overview.annotation_types` invites content-informativeness inference it cannot support

**Where:** [tools.py:820](../../multiomics_explorer/mcp_server/tools.py#L820)

```python
annotation_types: list[str] = Field(
    default_factory=list,
    description="Ontology types with annotations (e.g. ['go_bp', 'ec', 'kegg'])")
```

This field is **presence-by-source only** — it lists which ontology source has at
least one term for the gene. It does **not** indicate term content informativeness.
A `cog_category` entry on a hypothetical-protein gene almost certainly means
"Function unknown" — uninformative. A `tigr_role` entry usually means "Hypothetical
proteins / Conserved" — uninformative. A `pfam` entry can be "Domain of unknown
function (DUF…)" — uninformative.

The field name + description tell none of this. F2 in the trigger analysis is the
direct consequence: the LLM partitioned the 116 candidates into "informative /
hypclass-only / no ontology" using `annotation_types` as the discriminator and
got 16 / 116 misclassifications because the source presence does not predict term
content.

**Why it matters.** This is the single highest-leverage MCP-side finding from the
trigger analysis. Field-level disclosure of "what you can't infer from this" is
the exact thing the user asked the audit to surface.

**Fix shape — three layers, in order of cost:**

1. **(XS) Tighten the field description.** "Ontology source types where this gene
   has at least one annotation. **Presence-by-source only — a `cog_category`
   entry may be 'Function unknown'.** For term content, call `gene_ontology_terms`."
2. **(S) Add a sibling field at the result row.** `informative_annotation_types`
   = subset of `annotation_types` whose terms are not in a known catch-all list
   ("Function unknown", "Conserved hypothetical proteins", "Hypothetical proteins
   / Conserved", DUF*, "Protein of unknown function*", "uncharacterized protein"
   etc.). The catch-all list is small and stable. Lets the LLM make the partition
   the trigger analysis tried to make, correctly.
3. **(M) Add an envelope rollup.** `informativeness_breakdown:
   {informative: 16, catchall_only: 67, no_ontology: 17}` over the requested
   locus_tags. Removes the partition-construction work from user code entirely.

(1) is the doc-only fix. (2) and (3) are envelope-shape changes — the user's
"b" track already addresses some envelope normalization separately; this finding
intersects.

---

### F-AUDIT-3 (MED) — `gene_overview` docstring has upstream signposting but not downstream drill-down direction

**Where:** [tools.py:904-908](../../multiomics_explorer/mcp_server/tools.py#L904-L908)

```python
"""Get an overview of genes: identity and data availability signals.

Use after resolve_gene, genes_by_function, genes_by_ontology, or
gene_homologs to understand what each gene is and what follow-up
data exists.
"""
```

The docstring tells the LLM what tools come **before** `gene_overview`. It does not
tell the LLM what tools come **after** when a follow-up signal is present. Each
of the gene_overview output fields gestures at a richer tool that goes deeper:

| field | drill-down tool | currently signposted in field description? |
|---|---|---|
| `annotation_types` | `gene_ontology_terms` | no |
| `cluster_membership_count` / `cluster_types` | `gene_clusters_by_gene` | no |
| `closest_ortholog_group_size` / `closest_ortholog_genera` | `gene_homologs` | no |
| `derived_metric_count` / `derived_metric_value_kinds` | `gene_derived_metrics`, `genes_by_{kind}_metric` | **yes** (line 835: "Use to route to genes_by_{kind}_metric drill-downs") |
| `expression_edge_count` / `significant_*_count` | `differential_expression_by_gene`, `gene_response_profile` | no |

The DM fields show the model. The pattern is a one-line "for X, drill into Y"
clause on each summary field, plus a docstring tail listing downstream tools
matched to the upstream-tool listing.

**Compare** to `gene_details` ([tools.py:978-979](../../multiomics_explorer/mcp_server/tools.py#L978-L979)):

```
For organism taxonomy, use list_organisms. For homologs, use
gene_homologs. For ontology annotations, use gene_ontology_terms.
```

— this is the model. Promote to all summary tools.

**Fix shape:** add per-field drill-down clauses to `GeneOverviewResult`; add
downstream-tool list to `gene_overview` docstring tail.

**Generalization:** every summary-grain tool with rich envelope rollups should
follow the same pattern. Audit pass on `list_experiments`, `list_publications`,
`list_organisms`, `list_clustering_analyses`, `list_derived_metrics`.

**Audit cost to fix:** S — coordinated docstring edits across ~10 fields and
~5 tools.

---

### F-AUDIT-4 (MED) — `gene_details.results` is `list[dict]` — schema-untyped; field list lives in free prose

**Where:** [tools.py:950](../../multiomics_explorer/mcp_server/tools.py#L950)

```python
results: list[dict] = Field(
    default_factory=list,
    description="One row per gene — all Gene node properties via g{.*}. "
                "~30 fields including locus_tag, gene_name, product, "
                "organism_name, gene_category, annotation_quality, "
                "function_description, catalytic_activities, "
                "transporter_classification, cazy_ids, etc. "
                "Sparse fields only present when populated.")
```

Compared to `gene_overview` which has a strongly-typed `GeneOverviewResult` with
each field's purpose + example documented, `gene_details` exposes a black-box
dict. To know what fields are populated for what kinds of genes the LLM has to
(a) read the prose enumeration with its unhelpful "etc.", (b) call the tool and
inspect, or (c) read `kg_schema` and reverse-engineer.

This bites Q2 (proteome/transcriptome discordance) directly: the analysis needs
`Polypeptide.sequence_length`, `Polypeptide.molecular_mass`,
`Polypeptide.signal_peptide`, `Polypeptide.transmembrane_regions`,
`Polypeptide.is_reviewed`, `Polypeptide.annotation_score`. None of these are
listed in the docstring or schema. The analysis notebook had to itemize them
from prior knowledge of the KG schema rather than from the tool description.

**Aggravating factor.** The description uses Cypher syntax `g{.*}` — readable
to a developer but jargon for an LLM expected to interpret it correctly. (Same
issue at [tools.py:950](../../multiomics_explorer/mcp_server/tools.py#L950).)

**Fix shape:** extract a typed `GeneDetailResult` Pydantic model with each
field documented. Sparse Polypeptide.* fields are discoverable from
`Gene-[:HAS_POLYPEPTIDE]->Polypeptide` in the KG; enumerate them. Drop the `g{.*}`
phrasing from the description.

**Audit cost to fix:** M — schema work plus regen, but no behavioral changes.

---

### F-AUDIT-5 (MED) — `list_experiments.gene_count` semantics now documented but the *name* still primes the LLM to misread

**Where:** [tools.py:1763-1764](../../multiomics_explorer/mcp_server/tools.py#L1763-L1764)

The description is now clear: `gene_count` = "Cumulative row count across
timepoints" with explicit `distinct_gene_count` sibling. **This is a fix already
shipped per `2026-04-25-b2-explorer-improvements-design.md` item #2** — credit to
the b2 retrospective.

The remaining friction is the **name**: "gene_count" in a fresh LLM's reading
predicts "number of genes," not "row count summed across timepoints." A fresh
LLM scanning the catalog for "how many genes are in this experiment?" reaches
for `gene_count` first and would only catch the "actually you wanted
distinct_gene_count" via the docstring.

**Fix shape (consider for later):** rename to `cumulative_row_count` (or
`row_count` with `distinct_gene_count` becoming `gene_count`). Breaking change
— defer until other rename-class changes batch.

**Status:** documentation is fine; name is a deferred polish item, not a
near-term action.

---

### F-AUDIT-6 (MED) — Empty results don't distinguish "out of pipeline scope" from "no hits"

**Where:** every `_by_X` and `gene_*` tool. Concrete example: F3 in the trigger
analysis — `TX50_RS09500` returned empty `gene_homologs.no_groups`,
`gene_clusters_by_gene.not_matched`, `gene_ontology_terms` 0 rows.

The LLM correctly reported "no data on these axes." But the *reason* it had no
data is that the cyanorak / eggNOG / clustering pipelines were run on the
PMM-locus-tag set without reprocessing for late-added RefSeq entries. The gene
exists in the KG; the gene was simply outside the *scope* of the upstream
pipelines that populate these edges. From the API surface, a fresh LLM
cannot distinguish:

| LLM sees | Reality |
|---|---|
| `gene_homologs.no_groups: ['TX50_RS09500']` | Gene exists, ortholog pipeline didn't process it |
| `gene_homologs.no_groups: ['PMM_xyz']` (hypothetical) | Gene exists, ortholog pipeline ran on it but found no group |
| `gene_homologs.not_found: ['BAD_TAG']` | Gene doesn't exist in KG at all |

Two of these three are conflated under `no_groups`. The KG-side fix is to
re-run pipelines on the full locus-tag set (the trigger analysis's F3 already
proposes this); the *MCP-side* fix is to surface the distinction even if KG
doesn't.

**Fix shape:** add `out_of_pipeline_scope` envelope key (or per-row flag) on
tools that return empty for "pipeline didn't process this" cases. Requires KG
to track pipeline-scope per gene (currently inferable only by locus-tag prefix
heuristic). Deferable until the KG-side F3 remediation is decided.

**Status:** flagged for the joint KG+MCP design conversation.

---

### F-AUDIT-7 (LOW) — Paired-omics publications are not first-class; assembled from `omics_types` per publication

**Where:** Q2 walk. The user's first task was to identify which publications carry
matched RNA-seq + proteomics + cluster experiments. The actual workflow
(notebook step 1):

```
list_publications(limit=50)
list_experiments(publication_doi=[DOI], verbose=True)
list_derived_metrics(summary=True)
```

— inspect each pub's `omics_types` for the `RNASEQ + PROTEOMICS` intersection.

There's no `list_publications(has_paired_omics=True)` filter, no boolean field
on `PublicationResult`, no `paired_omics_pairs` rollup. The LLM has to assemble
the concept by hand. A first-class field would let `pathway_enrichment` /
discordance / paired-derived-metric workflows lead with `list_publications`
directly.

**Fix shape — choose one:**

1. Add `paired_omics_combinations: list[list[str]]` to `PublicationResult`
   (e.g., `[["RNASEQ", "PROTEOMICS"]]`).
2. Add a `has_paired_omics` boolean — coarser but cheaper.
3. Add envelope rollup `by_paired_omics` on `list_publications`.

Probably (1) — most informative, lowest naming-debate cost.

**Status:** new finding from Q2 walk. Worth a small spec.

---

### F-AUDIT-8 (LOW) — `annotation_quality` filter location is unsignposted

**Where:** Q1 walk. The trigger analysis filtered to AQ ≤ 1 from the 405 sig_up
genes. The field lives on `gene_overview` results
([tools.py:818](../../multiomics_explorer/mcp_server/tools.py#L818)) and is
populated for all 405 genes. But:

- `annotation_quality` is not in the catalog tool descriptions or in any tool's
  *parameter list*. A fresh LLM searching for "filter genes by annotation
  quality" finds no entry point.
- The field is on the response of `gene_overview`, but `gene_overview` doesn't
  *filter* by it — the LLM has to fetch all candidates, then filter client-side.
- `genes_by_function` doesn't expose `annotation_quality` as a filter, and
  neither does `differential_expression_by_gene`.

The trigger analysis worked around this by fetching `gene_overview` for all 405
sig_up genes and filtering in Python. Fine at this scale, awkward as discovery.

**Fix shape — choose:**

1. Add `annotation_quality_max` filter to `genes_by_function` and
   `differential_expression_by_gene`. Keeps the field's
   "data-availability-signal" character on `gene_overview` but lets discovery
   tools route on it.
2. Document `annotation_quality` in `list_filter_values` even though it's
   numeric, with the value semantics (`0=pure hypothetical, 1=desc only,
   2=named product, 3=well-annotated`).
3. Both.

**Status:** new finding from Q1 walk. Could fold into a "discovery tool filter
parity" spec covering this and similar gaps.

---

### Folded supporting evidence — Q3 (`pathway_enrichment_b2/api_coverage.md`)

The Q3 analysis already documented its own friction. Items not already covered
by `2026-04-25-b2-explorer-improvements-design.md`:

- **`list_experiments` doesn't expose authors.** Must join with `list_publications`
  for `first_author`. Noted at api_coverage.md L17. Could add `authors: list[str]`
  to `ExperimentResult`. (LOW.)
- **`ontology_landscape` doesn't distinguish flat vs hierarchical-tree vs DAG
  ontologies.** In the b2 spec as a long-term track item (`#4 → LT`); listed
  here for completeness.
- **`enrichment_all.csv` has NaN `omics_type` for Weissberg T experiments.**
  Upstream-KG fix per b2 spec; not MCP-actionable.

## Cross-cutting patterns

These are the systemic shapes behind individual findings — useful as a rubric
for evaluating new tools.

### P1 — Field examples can normalize bad data

The `Alternative locus ID` example (F-AUDIT-1) is the worst offender. General
rule: a field example is, for the LLM, a *prediction* of what real values look
like. If the example is a placeholder, the LLM cannot tell it apart from a
real value when one shows up in a response.

**Rubric clause:** field examples must be real, content-bearing values from the
KG. Never use known-placeholder, known-stub, or known-default strings in
examples.

### P2 — "Presence" fields invite content inferences they don't support

`annotation_types` (F-AUDIT-2) is the canonical case. The general pattern: any
field that summarizes *whether* data exists in some shape, without summarizing
*what* the data is, will be misread as a content signal at some point.

**Rubric clause:** any presence-only summary field must say so explicitly:
"presence-only — does NOT indicate content quality / informativeness / shape /
[X]". Plus, where applicable, name the drill-down tool that surfaces the
content.

### P3 — Drill-down direction underexplained

Most tool docstrings cover the *upstream* direction ("use after X to do Y") but
omit the *downstream* direction ("after this, drill into Z to get W"). The DM
field on `gene_overview` shows the right model: a one-line
"to drill down, call genes_by_{kind}_metric" pointer right in the field
description. This pattern is missing on the older fields.

**Rubric clause:** every coarse-summary field must signpost its drill-down tool
by name. Every summary tool must include a downstream-tool clause in its
docstring tail.

### P4 — `list[dict]` erodes self-documentation

`gene_details.results` is the worst offender. When the response shape is known
(it is — Cypher returns specific properties), an untyped dict trades schema
clarity for nothing useful. The LLM has to discover field names by inspection.

**Rubric clause:** typed Pydantic models for response rows whenever the shape
is known. `list[dict]` only for genuinely unstructured payloads (raw cypher
results, etc.).

### P5 — "0 rows" is ambiguous

F-AUDIT-6. The same empty result can mean (a) gene has no data of this kind,
(b) gene was outside the upstream pipeline's scope, or (c) gene doesn't exist
at all. The KG-level distinction is real (the trigger analysis's F3 names the
specific case for ortholog/cluster pipelines); the API doesn't surface it.

**Rubric clause:** when "no result" can mean two different things, surface the
distinction structurally — distinct envelope keys (`not_found` vs `no_groups`
vs `out_of_pipeline_scope`), or per-row flags. Don't conflate.

## Suggested rubric for new and existing tools

Rolled up from P1–P5. A tool's response schema passes the rubric iff:

- [ ] **Field examples are real KG values** — not placeholders, not stubs, not "TBD".
- [ ] **Presence-only fields say so** — and name the drill-down tool that
      surfaces content.
- [ ] **Coarse-summary fields signpost the drill-down tool by name** in the
      field description (DM-field model).
- [ ] **Tool docstring includes downstream direction** — "after this, drill
      into Y to get Z" — not just upstream callers.
- [ ] **Response rows are typed Pydantic models** — not `list[dict]` —
      whenever the shape is known.
- [ ] **Empty-result shapes are unambiguous** — `not_found` ≠ `not_matched` ≠
      `no_groups` ≠ `out_of_pipeline_scope`, and each is documented.
- [ ] **Field name predicts shape** — `gene_count` should describe a count of
      genes; if it's a row count, name it `row_count` (F-AUDIT-5 deferred).
- [ ] **No Cypher-syntax jargon** in user-facing descriptions (`g{.*}` etc.).

This rubric should also be added to the `add-or-update-tool` skill once the
findings are accepted, so new tools land conformant.

## Summary table

| Finding | Severity | Cost | Status |
|---|---|---|---|
| F-AUDIT-1 — Pydantic examples ship F5 placeholder | HIGH | XS | New |
| F-AUDIT-2 — `annotation_types` invites content inference | HIGH | XS / S / M (3 layers) | New |
| F-AUDIT-3 — `gene_overview` lacks downstream drill-down | MED | S | New |
| F-AUDIT-4 — `gene_details.results: list[dict]` untyped | MED | M | New |
| F-AUDIT-5 — `gene_count` semantics doc'd, name still misleads | MED | M (rename) | b2 doc fix shipped; rename deferred |
| F-AUDIT-6 — empty results conflate "no hit" with "out of scope" | MED | M (KG+MCP) | Defer; pairs with KG-side F3 fix |
| F-AUDIT-7 — paired-omics not first-class | LOW | S | New |
| F-AUDIT-8 — `annotation_quality` filter unsignposted | LOW | S | New |

## Out of scope for this audit

- **Boundary normalization** of `"N/A"` and `"Alternative locus ID"` strings —
  user's separate "b" track.
- **Methodology / discipline** issues from F7-A2/A3 (drafted-from-memory,
  pre-architecting) — server-side has limited leverage; lives in skills.
- **The 25 tools not sampled in M3.** Patterns P1–P5 are likely to recur
  there; a follow-up sweep applying the rubric is warranted but not in this pass.

## Suggested next steps

1. **Pick HIGH findings to act on first.** F-AUDIT-1 and F-AUDIT-2 are the
   highest-leverage; F-AUDIT-1 is a 5-minute fix.
2. **Promote the rubric** into `add-or-update-tool/SKILL.md` once findings
   are accepted, so the audit's lessons compound on every new tool.
3. **Schedule a rubric-driven sweep** of the remaining 25 tools (separate
   pass; cheaper now that the rubric exists).
4. **Defer F-AUDIT-5, F-AUDIT-6** until naming/KG batches make them cheap.

This doc is a findings inventory — designs for individual fixes (or fix
batches) live in follow-on specs created via `superpowers:writing-plans` once
the user picks which subset to act on.
