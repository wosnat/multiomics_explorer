# Transition plan (v3)

How to get from the current state to the v3 target architecture.
See `architecture_target_v3.md` for the target,
`methodology/llm_omics_analysis_v3.md` for the design rationale,
`methodology/tool_framework.md` for the tool surface, and
`whats_changed_v3.md` for a summary of what changed from v1 and v2.

---

## Current state

The v2 transition was stopped mid-Phase D. Here's what's done
and what's not.

### Completed (v2 phases A–C + partial D)

- **Phase A** — Inactive modules removed, parameter/return naming
  standardized, api/ layer created, MCP tools rewired to call api/,
  error handling pattern, logging. Switched to `fastmcp>=3.0`.
- **Phase B** — Expression tools removed (`query_expression`,
  `compare_conditions`). Minimal Cypher updates for new KG schema
  (Experiment nodes, `Changes_expression_of` edges). New KG deployed.
- **Phase C** — Dev skills created and validated on simple tools:
  - `list_publications` (C2) — added via add-tool skill
  - `list_organisms` (C3) — upgraded to full v2 pattern (async,
    Pydantic models, ToolError, tags, Field descriptions, about
    content via build script)
  - Code review retrospective (C4) — skills updated with learnings
- **Phase D partial** — `list_experiments` built with summary/detail
  modes (D1). `resolve_gene` upgraded to v2 pattern. D2+ not done.

### What exists now

**Tools in v2 pattern** (async, Pydantic response models, ToolError,
Field descriptions, about content):

| Tool | Status |
|---|---|
| `list_organisms` | v2 complete |
| `list_publications` | v2 complete |
| `list_experiments` | v2 complete (has summary/detail modes) |
| `resolve_gene` | v2 complete |

**Tools in v1 pattern** (sync `def`, JSON string returns, `logger`,
no Pydantic models):

| Tool | Status |
|---|---|
| `get_schema` | v1 |
| `list_filter_values` | v1 |
| `search_genes` | v1 |
| `gene_overview` | v1 |
| `get_gene_details` | v1 (to be retired) |
| `get_homologs` | v1 (to be renamed `gene_homologs`) |
| `search_ontology` | v1 |
| `genes_by_ontology` | v1 |
| `gene_ontology_terms` | v1 |
| `run_cypher` | v1 |

**Tools not yet built:**

| Tool | Notes |
|---|---|
| `genes_by_function` | Replaces `search_genes` (rename + redesign) |
| `search_homolog_groups` | New — text search on OrthologGroup |
| `genes_by_homolog_group` | New — group ID → member genes |
| `differential_expression_by_gene` | Replaces removed `query_expression` |
| `differential_expression_by_ortholog` | New — cross-organism via homology |

### What changed between v2 and v3 architecture

The v3 docs introduce several changes that affect how remaining
tools should be built/migrated:

| v2 pattern | v3 pattern |
|---|---|
| `mode: Literal["summary", "detail"]` | `summary: bool` (sugar for `limit=0`) |
| MCP computes `returned`/`truncated` | api/ assembles complete response dict |
| `gene_id`/`gene_ids` params | `locus_tags` (always list) |
| MCP default `limit=50` | MCP default `limit=5` |
| No `not_found` field | Batch tools return `not_found` list |
| About content via tagged blocks | Auto-generated from Pydantic + YAML |
| Three modes (summary/detail/about) | `summary` bool + about via MCP resources |

**Already-migrated tools need updating** to match v3 conventions.
This is tracked in Phase H below.

See `whats_changed_v3.md` for the full v2→v3 delta.

---

## Tool target state

Each tool gets a full spec (`docs/tool-specs/{name}.md`) via Phase 1
of the add-or-update-tool skill before building. The table below is
the summary — enough to plan work, not enough to implement.

### Phase 1 — Orientation

| Target name | Current | Action | Phase | Batch | Summary fields | Key params |
|---|---|---|---|---|---|---|
| `list_organisms` | v2 | Align to v3 | H2 | No | total_entries | `verbose`, `limit` |
| `list_publications` | v2 | Align to v3 | H2 | No | total_entries, total_matching | `organism`, `treatment_type`, `search_text`, `author`, `verbose`, `limit` |
| `list_experiments` | v2 (has modes) | mode→summary | H1 | No | total_entries, total_matching, by_organism, by_treatment, by_omics | `organism`, `treatment_type`, `omics_type`, `search_text`, `summary`, `verbose`, `limit` |

### Phase 2 — Gene work: Discovery

| Target name | Current | Action | Phase | Batch | Summary fields | Key params |
|---|---|---|---|---|---|---|
| `resolve_gene` | v2 | Align to v3 | H2 | No | total_matching | `identifier`, `organism`, `limit` |
| `genes_by_function` | `search_genes` (v1) | Rename + v3 | D3 | No | total_matching, by_organism, by_category | `search_text`, `organism`, `category`, `summary`, `verbose`, `limit` |
| `genes_by_ontology` | v1 | v3 upgrade | D4 | No | total_matching, by_organism, by_term | `term_ids`, `organism`, `summary`, `verbose`, `limit` |
| `genes_by_homolog_group` | — | New | E1 | Yes (`group_ids`) | total_matching, by_organism | `group_ids`, `verbose`, `limit`, `not_found` |

### Phase 2 — Gene work: Details

| Target name | Current | Action | Phase | Batch | Summary fields | Key params |
|---|---|---|---|---|---|---|
| `gene_overview` | v1 | v3 upgrade | D4 | Yes (`locus_tags`) | total_matching, annotation_type_breakdown, expression_availability | `locus_tags`, `verbose`, `limit`, `not_found` |
| `gene_ontology_terms` | v1 | v3 upgrade | D4 | Yes (`locus_tags`) | total_matching | `locus_tags`, `ontology`, `verbose`, `limit`, `not_found` |
| `gene_homologs` | `get_homologs` (v1) | Rename + v3 | D2 | Yes (`locus_tags`) | total_matching | `locus_tags`, `source`, `taxonomic_level`, `verbose`, `limit`, `not_found` |

### Phase 2 — Gene work: Annotation

| Target name | Current | Action | Phase | Batch | Summary fields | Key params |
|---|---|---|---|---|---|---|
| `search_ontology` | v1 | v3 upgrade | D4 | No | total_matching | `search_text`, `ontology`, `limit` |
| `search_homolog_groups` | — | New | E1 | No | total_matching | `search_text`, `source`, `limit` |

### Phase 3 — Expression

| Target name | Current | Action | Phase | Batch | Summary fields | Key params |
|---|---|---|---|---|---|---|
| `differential_expression_by_gene` | — | New | E2 | Yes (`locus_tags`, `experiment_ids`) | total_matching, direction_breakdown, median_log2fc, top_categories | `experiment_ids`, `locus_tags`, `direction`, `significant_only`, `summary`, `verbose`, `limit` |
| `differential_expression_by_ortholog` | — | New | E2 | Yes (`group_ids`, `experiment_ids`) | total_matching, direction_breakdown, organism_coverage, conservation_pattern | `experiment_ids`, `group_ids`, `direction`, `significant_only`, `summary`, `verbose`, `limit` |

### Utils

| Target name | Current | Action | Phase | Batch | Summary fields | Key params |
|---|---|---|---|---|---|---|
| `kg_schema` | `get_schema` (v1) | Rename + v3 | D4 | No | — | — |
| `list_filter_values` | v1 | v3 upgrade | D4 | No | — | — |
| `run_cypher` | v1 | v3 upgrade | D4 | No | — | `query`, `limit` (default 25) |

### Retiring

| Tool | Replacement | Phase |
|---|---|---|
| `get_gene_details` | `gene_overview` (batch, richer) | D5 |

---

## Remaining transition phases

### Phase H: Align v2 tools with v3 conventions

Update the 4 tools already in v2 pattern to match v3 conventions.
Small changes per tool — the bulk of the work (async, Pydantic,
ToolError) is already done.

#### H1: `list_experiments` — mode → summary bool

Currently uses `mode: Literal["summary", "detail"]`. Update to:
- `summary: bool = False` parameter (both api/ and MCP)
- api/ assembles complete response dict (move `returned`/`truncated`
  computation from MCP to api/)
- Default `limit=5` in MCP

**Gate:** All tests pass. Code review (code-review skill) passes.

#### H2: `list_organisms`, `list_publications`, `resolve_gene`

These don't have modes, but need:
- api/ to return `returned`/`truncated` (currently computed in MCP)
- Default `limit=5` in MCP (currently 50)
- `resolve_gene`: batch tool → add `not_found` when
  accepting lists (currently accepts single `identifier` — no
  change needed now, but note for future if it gains batch input)

**Gate per tool:** All tests pass. Code review passes.

#### H3: Update dev skills + checklist templates

Already done in this session. Verify skills match actual code
after H1-H2 changes.

---

### Phase D (continued): Migrate remaining v1 tools

Pick up where v2 transition left off. Each tool follows the
add-or-update-tool skill, which includes KG exploration (Step 2)
and KG spec writing when schema changes or precomputed stats are
needed. KG work is incremental — each tool defines what it needs
from the KG, writes a spec if needed, and waits for the KG rebuild
before building Phase 2. No separate "precomputed stats" phase.

Each tool in Phase D follows the add-or-update-tool skill and gets
a code review (code-review skill) immediately after. Fix issues
before moving to the next tool. Update skills if the review
reveals gaps.

#### D2: `get_homologs` → `gene_homologs` (rename + v3 upgrade)

- Rename across all layers (cascading rename)
- Upgrade to v3 pattern (async, Pydantic, summary bool, api/ owns
  response dict)
- `locus_tags` parameter (list, not single `gene_id`)
- `not_found` for missing genes
- About content via input YAML + build script

**Gate:** All tests pass. Code review passes. Old name removed.

#### D3: `search_genes` → `genes_by_function` (rename + v3 upgrade)

- Rename across all layers
- Upgrade to v3 pattern
- Rich summary fields (organism breakdown, category breakdown)
- Default `limit=5`

**Gate:** All tests pass. Code review passes.

#### D4: Remaining v1 tools → v3 pattern

Migrate each to v3 (order flexible). Code review after each tool.

| Tool | Key changes |
|---|---|
| `gene_overview` | Batch tool: add `not_found`, `summary` bool, rich summary fields (annotation type breakdown) |
| `search_ontology` | v3 upgrade, summary fields if large results |
| `genes_by_ontology` | v3 upgrade, rich summary fields |
| `gene_ontology_terms` | Batch tool: `locus_tags` list, `not_found` |
| `get_schema` → `kg_schema` | Rename + v3 upgrade |
| `list_filter_values` | v3 upgrade (simple, small result set) |
| `run_cypher` | v3 upgrade (keep limit=25 default) |

**Gate per tool:** Tests pass. Code review passes.

#### D5: Retire `get_gene_details`

- Remove from all layers
- Update CLAUDE.md
- `gene_overview` covers the use case; `run_cypher` for edge cases

**Gate:** All references removed. Code review confirms clean removal.

---

### Phase E: New tools (from tool_framework.md)

Build the tools that don't exist yet. Each tool follows the
add-or-update-tool skill — Phase 1 (definition) includes KG
exploration and KG spec writing. If the tool needs new KG
properties or precomputed stats, the KG spec is written, the KG
is rebuilt, then Phase 2 (build) proceeds. KG work is incremental,
driven by each tool's needs.

#### E1: Homology tools

Phase 1 (definition) explores what OrthologGroup nodes currently
have and writes KG specs for anything missing (`consensus_gene_name`,
`consensus_product`, `genera`, `member_count`, `specificity_rank`,
fulltext index on consensus fields).

| Tool | Type | KG needs |
|---|---|---|
| `search_homolog_groups` | New — text search on OrthologGroup | Fulltext index on consensus fields |
| `genes_by_homolog_group` | New — group ID → member genes | OrthologGroup properties populated |

**Gate per tool:** Tests pass. Code review passes. Homology triplet
(search → by_group → gene_homologs) chains correctly.

#### E2: Expression tools

Phase 1 (definition) explores the expression schema and writes KG
specs for precomputed stats needed on Experiment and OrthologGroup
nodes. KG spec defines what to precompute; KG rebuild adds the
properties; then the tool is built to read them.

| Tool | Type | KG needs |
|---|---|---|
| `differential_expression_by_gene` | New — gene × experiment × timepoint | Experiment precomputed stats (`gene_count`, `significant_count`, time_point arrays) |
| `differential_expression_by_ortholog` | New — cluster × experiment, cross-organism | OrthologGroup stats (`expression_experiment_count`, `expression_organism_count`, `conservation_pattern`) |

Build `by_gene` first (simpler), then `by_ortholog` (requires
ortholog group selection algorithm). Code review after each.

**Gate per tool:** Tests pass. Code review passes. Summary fields
include direction breakdown, top categories, median |log2FC|.
Summary field consistency tests verify precomputed stats match
actual data.

---

### Future phases (after all tools are built)

#### Phase F: Research skills

Build on top of the working tools. Not scoped yet — depends on
tool surface being complete.

- F1: Layer 1 — `multiomics-kg-guide` (organize about content
  into agentskills.io structure, `sync_skills.sh`)
- F2: Layer 2 — Pipeline skill drafts (`characterize-experiment`,
  `gene-survey`, `compare-conditions`, `ortholog-conservation`,
  `timecourse-analysis`, `export-de-genes` — with `methods.md`
  templates)
- F3: Layer 3 — Inversion skill draft
  (`clarify-research-question`)
- F4: MCP server instructions (layer 1 content for chat mode)

#### Phase G: Packaging + deployment

- G1: `init-claude` command
- G2: Usage logging (storage mechanism TBD)
- G3: Final docs cleanup (remove v2, rename v3, update CLAUDE.md)

---

## Step dependencies

```
Phase H: Align v2 tools with v3 (quick)
  H1 (list_experiments mode→summary) → H2 (other v2 tools) → H3 (verify skills)

Phase D: Migrate v1 tools (after H)
  D2 (gene_homologs) → D3 (genes_by_function) → D4 (remaining)
    → D5 (retire get_gene_details)
  Code review after each tool. KG spec if tool needs schema changes.

Phase E: New tools (after D)
  E1 (homology tools) — KG spec → KG rebuild → build tools
  E2 (expression tools) — KG spec → KG rebuild → build tools
  E1 and E2 can proceed in parallel if KG supports both
  KG work is incremental — each tool's Phase 1 writes the KG spec

Phase F, G: Future — after all tools are built
```

**Quick wins (Phase H):** Small changes to align existing v2 tools
with v3 conventions. Can be done immediately.

**Parallel opportunities:**
- E1 (homology tools) and E2 (expression tools) are independent
  if KG supports both
- D-phase tools are mostly independent of each other (order flexible)

---

## Coordinated work with KG repo

KG changes are driven by tool needs. Each tool's Phase 1 (definition)
writes a KG spec if needed (`docs/kg-specs/kg-spec-{tool}.md`).
The KG rebuild happens before Phase 2 (build) of that tool.

| Tool | KG spec needed | Coordination |
|---|---|---|
| D2: `gene_homologs` | Maybe — verify OrthologGroup properties exist | Check before build |
| D4: `gene_overview` | Maybe — precomputed annotation stats | KG spec if adding stats |
| E1: homology tools | Fulltext index + OrthologGroup properties | KG spec → rebuild → build |
| E2: `differential_expression_by_gene` | Experiment precomputed stats | KG spec → rebuild → build |
| E2: `differential_expression_by_ortholog` | OrthologGroup expression stats | KG spec → rebuild → build |

D-phase tools may not need KG changes (existing schema may suffice).
E-phase tools will almost certainly need KG specs.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| v2→v3 convention changes break existing v2 tools | H1-H2 are small, focused changes with tests |
| Cascading renames (D2, D3) miss references | Grep before rename; regression tests catch drift |
| Expression tools (E2) are complex to build | Build `by_gene` first (simpler), validate, then `by_ortholog` |
| Precomputed stats drift from actual data | Summary field consistency tests; regenerate on every KG rebuild |
| About content drifts from tool behavior | Auto-generated from Pydantic models; tests verify consistency |
| Skills too prescriptive or not enough | Phase 2 stress testing (separate repo) refines before shipping |
