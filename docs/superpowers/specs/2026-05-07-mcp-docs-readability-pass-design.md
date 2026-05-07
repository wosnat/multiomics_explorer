# MCP outfacing-docs readability pass

**Status:** design / approved-style-rules
**Date:** 2026-05-07
**Audience:** an LLM agent calling MCP tools. Optimize for correctness signal density, not human prose.

---

## Goal

Sweep all 37 MCP tools so their **outfacing surfaces** read as a clean,
self-consistent toolset rather than as an archaeology layer of past
specs, audits, and KG releases. The agent's view of each tool comes
from three places that all flow through `scripts/build_about_content.py`:

1. **Tool docstring** — the `description` returned by `mcp.list_tools()`,
   shown to the agent at tool-listing time. Lives in
   `mcp_server/tools.py`.
2. **Pydantic field `description=`** — the per-parameter and per-result
   field descriptions, surfaced in the params table and per-result
   table of the generated md. Lives in `mcp_server/tools.py`.
3. **Per-tool YAML** — examples, common mistakes, chaining patterns,
   `verbose_fields`, optional `response_notes`. Lives in
   `multiomics_explorer/inputs/tools/{tool}.yaml`.

After edits, regenerate `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{tool}.md`
via `uv run python scripts/build_about_content.py`.

The two upper-Layer surfaces (`kg/queries_lib.py`, `api/functions.py`)
are not outfacing. Out of scope.

---

## Style rules (locked, applied uniformly)

1. **No time-stamped counts.** "149 metabolites today", "3,025 today",
   "22 such metabolites today" → either delete, or rephrase as a stable
   shape ("a small subset", "metabolomics-only metabolites have
   gene_count=0"). Counts that are structurally bounded (Literal-set
   sizes, tuple lengths) stay.
2. **No internal-history shorthand.** No `§`, `Phase N`, `audit §`,
   `F1`/`D2`/`D8`, `KG-MET-002`, `Mode-B`, `Cluster A`, `parent §10`.
   If the underlying constraint matters, restate it in plain words.
3. **No release-date hedges, with one carveout.** "renamed from `search`
   in Phase 2", "(KG release 2026-05-06)", "(2026-05-03 rollup)" →
   delete. **Carveout:** the `[AQ]` (annotation_quality redefinition)
   and `[ENR]` (`informative_only=True` default flip) drift markers
   stay as 1-line inline notes on affected tools (`genes_by_function`,
   `gene_details`, `gene_overview`, `pathway_enrichment`,
   `cluster_enrichment`, the 4 ontology tools). They flag silent
   semantic drift across KG releases — an agent's session memory or
   prior runs may produce divergent results, and the inline reminder
   is cheaper to read than a cross-link fetch.
4. **Cross-link only by stable URI.** `docs://analysis/...`,
   `docs://guide/...`, peer tool names — yes. Internal commit SHAs,
   plan filenames, "spec §X" — no.
5. **De-duplicate.** One canonical home per fact. If a Pydantic field
   description already states the rule, don't restate it in the YAML
   `mistakes`. Tool docstring covers identity + routing; field
   descriptions cover field-scoped semantics; YAML `mistakes` covers
   only cross-field gotchas the agent gets wrong.
6. **Pydantic field descriptions stay terse.** Lead = type/semantics;
   second clause ≤ 1 example; no narrative. Read in tooltip-sized
   contexts.
7. **Docstrings stay tight.** A docstring is the MCP tool's
   `description` shown on tool-listing. Aim for **1 paragraph + 1
   routing sentence**. Defer dense prose to the per-tool md (which the
   agent fetches via `docs://tools/{name}` only when it commits to
   using the tool).
8. **CLAUDE.md tool-table rows out of scope.** They're internal-team
   notes, not outfacing.
9. **Defer to guides for cross-cutting semantics — but with two
   non-negotiable inline carveouts.** What gets cross-linked-only:
   multi-paragraph explanations in the **tool docstring** or in YAML
   `mistakes:` that the guides already cover at length (tested-absent,
   transport-confidence, direction-agnosticism, AND-vs-UNION,
   summary/verbose modes, pagination, BRITE-tree-scoping, organism
   naming, Lucene scoring, AQ redefinition, informative_only default,
   DM family gating). Replace with one pointer per relevant guide URI.

   **Inline carveouts (do NOT cross-link, restate in 1 clause):**

   - **Pydantic field descriptions** (params table + per-result
     fields). The agent reads field-by-field, not top-to-bottom. A
     cross-link costs a second fetch and the agent may skip it.
     Each `Field(description=...)` states the relevant slice inline.
     Example: `organism_names` description gets its own 1-clause
     "exact, case-insensitive on `preferred_name`" — not a pointer to
     `docs://guide/conventions#organism-naming`.
   - **One-line YAML gotchas.** If the entry is already 1 sentence, a
     cross-link is more expensive than the gotcha itself — keep
     inline. Cross-link kicks in for entries that span paragraphs.

   Per-tool docs always preserve **tool-specific deviation** from the
   guide rule (e.g. `differential_expression_by_gene` mentions the
   `table_scope` interaction with tested-absent rows; `list_metabolites`
   mentions the `organism_names` UNION vs `elements` AND-of-presence
   asymmetry).

The four guide files at `docs://guide/{start_here, concepts,
conventions, python_api}` are the authoritative cross-cutting doc;
treat them as the shared preamble that every per-tool doc inherits.

---

## What stays (do not strip)

- Per-row routing fields and what triggers a drill-down.
- Filter combinatorics specific to one tool (e.g. `genes_by_metabolite`
  per-arm scope of `ec_numbers`).
- Specific gotchas the agent will get wrong without a warning
  (currency-cofactor noise, `family_inferred` dominance, full
  `preferred_name` vs short organism name).
- Concrete IDs in examples (`"kegg.compound:C00031"`).
- Worked few-shot examples (whole point of YAML `examples:`).

The compression target is **internal-archaeology language**, not
correctness signal.

---

## Edit surfaces

### Layer 3 — `mcp_server/tools.py`

- Tool docstrings (the `"""..."""` directly under each
  `@mcp.tool()` function or its FastMCP-registered helper).
- Pydantic `Field(description=...)` strings on:
  - Function parameters annotated via `Annotated[..., Field(...)]`
  - Per-result Pydantic models (e.g. `MetaboliteResult`, `GbmTopGene`,
    `ListMetabolitesResponse`).
- Where a docstring is currently exhaustively re-explaining a
  cross-cutting convention, replace with a one-line pointer
  (`See docs://guide/conventions for ...`). Keep only the tool-specific
  spin.

### Layer 4 — `multiomics_explorer/inputs/tools/{tool}.yaml`

- `mistakes:` — drop entries that restate a Pydantic field
  description; keep entries that describe cross-field interactions
  the agent will get wrong.
- `chaining:` — already terse on most tools; remove time-stamped
  notes if any (`(2026-05-03 rollup)` etc).
- `examples:` — remove inline editorial like
  `# Phase 1 plumbing — spec §6.6`.
- `response_notes:` — same de-stamp pass.

### Regeneration

After each batch:

```bash
uv run python scripts/build_about_content.py
```

Diff `multiomics_explorer/skills/multiomics-kg-guide/references/tools/`
to confirm the rendered md reflects the source edits and nothing
else moved.

`scripts/build_about_content.py` itself is **out of scope**. The
renderer is correct; only its inputs need editing. (Optional follow-up:
a `--lint` mode that warns on style violations — separate ticket.)

---

## Batches

1. **Batch 1 — high-traffic discovery + identity (9 tools)**
   `kg_schema`, `resolve_gene`, `gene_overview`, `gene_details`,
   `genes_by_function`, `list_organisms`, `list_publications`,
   `list_experiments`, `list_filter_values`.
2. **Batch 2 — chemistry + metabolomics (7 tools)**
   `list_metabolites`, `list_metabolite_assays`, `genes_by_metabolite`,
   `metabolites_by_gene`, `metabolites_by_quantifies_assay`,
   `metabolites_by_flags_assay`, `assays_by_metabolite`.
3. **Batch 3 — DE / DM / orthology / clustering (14 tools)**
   `differential_expression_by_gene`,
   `differential_expression_by_ortholog`, `gene_response_profile`,
   `list_derived_metrics`, `gene_derived_metrics`,
   `genes_by_numeric_metric`, `genes_by_boolean_metric`,
   `genes_by_categorical_metric`, `gene_homologs`,
   `search_homolog_groups`, `genes_by_homolog_group`,
   `gene_clusters_by_gene`, `genes_in_cluster`,
   `list_clustering_analyses`.
4. **Batch 4 — ontology + enrichment + cypher (7 tools)**
   `search_ontology`, `ontology_landscape`, `genes_by_ontology`,
   `gene_ontology_terms`, `pathway_enrichment`, `cluster_enrichment`,
   `run_cypher`.

Per-batch loop:

1. Edit Pydantic descriptions and tool docstrings in
   `mcp_server/tools.py`.
2. Edit `inputs/tools/{tool}.yaml` per the rules above.
3. Run `uv run python scripts/build_about_content.py` (it rebuilds
   only tools with input YAMLs by default — sufficient).
4. Run `pytest -m "not kg" -q` as a smoke pass (Pydantic schemas
   compile cleanly, `register_tools` round-trips).
5. Commit per batch:
   `docs(mcp): readability pass batch N — <surface>`.

Final batch ends with one verification pass over the four guide files
to confirm no contradictions opened up.

---

## Out of scope

- `kg/queries_lib.py`, `api/functions.py` (not outfacing).
- `CLAUDE.md` tool table (internal-team).
- `scripts/build_about_content.py` (renderer is fine; possible
  optional `--lint` follow-up flagged separately).
- Behavior changes. **No tool semantics change.** If editing surfaces
  the fact that a description is *wrong*, fix the description; do not
  silently change tool behavior.
- The four guide files (`docs://guide/*`) — already restructured in
  commit `8d85962`. Touch only if a per-tool edit reveals a
  contradiction; in that case, prefer fixing the per-tool side unless
  the guide is wrong.
- Analysis md (`skills/.../references/analysis/*`) — separate
  hand-authored surface, not part of this pass.

---

## Verification

- `pytest -m "not kg" -q` clean after each batch.
- `git diff --stat` per batch shows the expected three-file pattern
  (tools.py + 1+ yamls + 1+ regenerated md per tool).
- Final pass: spot-check `docs://tools/list_metabolites`,
  `docs://tools/pathway_enrichment`,
  `docs://tools/genes_by_metabolite` (the three densest pages today)
  against the 9 style rules.

---

## Done definition

- All 37 tool docstrings + Pydantic field descriptions + per-tool
  YAMLs reviewed against the 9 rules.
- All `skills/.../references/tools/*.md` regenerated; diff shows only
  the expected source edits.
- No remaining matches in the rendered md for the lint regexes:
  `\d{4}-\d{2}-\d{2}` (date stamps),
  `Phase \d+` (phase refs), `§`, `audit`, `KG-[A-Z]+-\d+`,
  ` today` (leading-space avoids false positives in normal English).
- Tests green; CLAUDE.md rows untouched; the four guide files
  unchanged.
