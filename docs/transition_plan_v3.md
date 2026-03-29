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
| `list_organisms` | v3 complete |
| `list_publications` | v3 complete |
| `list_experiments` | v3 complete |
| `resolve_gene` | v3 complete |
| `gene_homologs` | v3 complete (was `get_homologs`) |
| `genes_by_function` | v3 complete (was `search_genes`) |
| `gene_overview` | v3 complete |
| `search_ontology` | v3 complete |
| `genes_by_ontology` | v3 complete |

**Tools in v1 pattern** (sync `def`, JSON string returns, `logger`,
no Pydantic models):

| Tool | Status |
|---|---|
| `get_schema` | v1 (to be renamed `kg_schema`) |
| `list_filter_values` | v1 |
| `get_gene_details` | v1 (to be retired) |
| `gene_ontology_terms` | v1 |
| `run_cypher` | v1 |

**Tools not yet built:**
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

#### H1: `list_experiments` — mode → summary bool ✅

#### H2: `list_organisms`, `list_publications`, `resolve_gene` ✅

#### H3: Update dev skills + checklist templates ✅

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

#### D2: `get_homologs` → `gene_homologs` (rename + v3 upgrade) ✅

- Rename across all layers (cascading rename)
- Upgrade to v3 pattern (async, Pydantic, summary bool, api/ owns
  response dict)
- `locus_tags` parameter (list, not single `gene_id`)
- `not_found` for missing genes
- About content via input YAML + build script

**Gate:** All tests pass. Code review passes. Old name removed.

#### D3: `search_genes` → `genes_by_function` (rename + v3 upgrade) ✅

- Rename across all layers
- Upgrade to v3 pattern
- Rich summary fields (organism breakdown, category breakdown)
- Default `limit=5`

**Gate:** All tests pass. Code review passes.

#### D4: Remaining v1 tools → v3 pattern

Migrate each to v3 (order flexible). Code review after each tool.

| Tool | Key changes | Status |
|---|---|---|
| `gene_overview` | Batch tool: `locus_tags`, `not_found`, `summary`/`verbose`/`limit`, rich summary fields (by_organism, by_category, by_annotation_type, has_expression/significant/orthologs). Verbose adds gene_summary, function_description, all_identifiers. | ✅ done 2026-03-23 |
| `search_ontology` | v3 upgrade: summary fields (total_entries, score_max/median), 2-query pattern, async, Pydantic. No verbose (all fields lightweight). No KG changes needed. | ✅ done 2026-03-23 |
| `genes_by_ontology` | v3 upgrade: summary fields (total_matching, by_organism, by_category, by_term), 2-query pattern, async, Pydantic, Literal ontology. Verbose adds matched_terms, gene_summary, function_description. | ✅ done 2026-03-23 |
| `gene_ontology_terms` | Batch tool: `locus_tags` list, `not_found`, `no_terms`, optional ontology filter, leaf-only (always), rich summary (by_ontology, by_term, annotation density stats). `leaf_only` param removed. | ✅ done 2026-03-24 |
| `get_schema` → `kg_schema` | Rename + v3 upgrade | ✅ done 2026-03-29 |
| `list_filter_values` | v3 upgrade (simple, small result set) | ✅ done 2026-03-29 |
| `run_cypher` | v3 upgrade (keep limit=25 default) | ✅ done 2026-03-29 |
| `gene_details` | New v3 tool — all Gene properties via `g{.*}`, batch `locus_tags`, summary/verbose/limit | ✅ done 2026-03-29 |

**Gate per tool:** Tests pass. Code review passes.

#### D5: Retire `get_gene_details` ✅

- `get_gene_details` removed from all layers (done 2026-03-29)
- Replaced by `gene_details` (new v3 tool with batch support)
- `gene_overview` remains the recommended entry point; `gene_details` for deep-dive

---

### Phase E: New tools (from tool_framework.md)

Build the tools that don't exist yet. Each tool follows the
add-or-update-tool skill — Phase 1 (definition) includes KG
exploration and KG spec writing. If the tool needs new KG
properties or precomputed stats, the KG spec is written, the KG
is rebuilt, then Phase 2 (build) proceeds. KG work is incremental,
driven by each tool's needs.

#### E1: Homology tools ✅

| Tool | Status |
|---|---|
| `search_homolog_groups` | ✅ done 2026-03-26 |
| `genes_by_homolog_group` | ✅ done 2026-03-27 |

Homology triplet (search → by_group → gene_homologs) chains correctly.

#### E2: Expression tools ✅

| Tool | Status |
|---|---|
| `differential_expression_by_gene` | ✅ done 2026-03-28 |
| `differential_expression_by_ortholog` | ✅ done 2026-03-29 |

Summary fields include direction breakdown, top categories/experiments, median |log2FC|.
Cross-organism ortholog expression working end-to-end.

---

### Next phases — tool surface complete, ready for validation

#### Phase 2 (roadmap): Stress test with real analysis

New local repo, use Claude Code as researcher. Validate the tool
surface with real biology questions before building skills or
packaging. This is the critical validation gate.

- Test multi-tool workflows (gene discovery → expression → orthologs)
- Identify tool gaps, ergonomic issues, missing summary fields
- Validate methodology doc patterns against real use
- Document workflow patterns that emerge

**Gate:** Confident the 18-tool surface supports real research
workflows. Issues logged and fixed before building skills.

#### Phase F: Research skills

Build on top of validated tools + workflow patterns from Phase 2.

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
Phase H: ✅ complete
Phase D: ✅ complete (D2–D5, all v1 tools migrated or retired)
Phase E: ✅ complete (E1 homology + E2 expression tools)

→ Phase 2 (roadmap): Stress test with real analysis questions
  → Phase F: Research skills (informed by Phase 2 findings)
    → Phase G: Packaging + deployment
```

**Current state:** All 18 tools built, smoke-tested end-to-end
(2026-03-29). Ready for Phase 2 validation.

---

## Coordinated work with KG repo

All KG specs written and KG rebuilt through E2. KG specs live in
`docs/kg-specs/`. Future KG changes will be driven by Phase 2
findings (e.g. missing properties discovered during real analysis).

---

## Risks and mitigations (forward-looking)

| Risk | Mitigation |
|---|---|
| Precomputed stats drift from actual data | Summary field consistency tests; regenerate on every KG rebuild |
| Tool surface has gaps for real workflows | Phase 2 stress testing catches these before building skills |
| Skills too prescriptive or not enough | Phase 2 stress testing (separate repo) refines before shipping |
