# Transition plan (v2)

How to get from the current state to the target architecture.
See `architecture_target_v2.md` for the target and
`methodology/llm_omics_analysis_v2.md` for the design rationale.

---

## Current state

Phase A of the original transition plan is complete (steps 1–7):
- Inactive modules removed (agents/, ui/, evaluation/, old api/)
- Parameter and return naming standardized
- api/ layer created with functions wrapping query builders
- `__init__.py` wired with public re-exports
- MCP tools rewired to call api/
- Error handling pattern (api/ raises ValueError, MCP catches)
- Logging added

Additional completed work:
- Switched from `mcp[cli]` to `fastmcp>=3.0`
- v2 methodology and architecture docs drafted

**What exists now:**

```
queries_lib.py  →  build_*() → tuple[str, dict]
     ↓
api/functions.py  →  build + execute → list[dict] or dict
     ↓
tools.py  →  calls api/, formats JSON text, applies limit
     ↓
MCP server  →  returns formatted text
```

- All tools use the **old KG schema** (EnvironmentalCondition nodes,
  split expression edge types)
- No summary/detail/about modes
- No skills
- No precomputed statistics in KG
- `fastmcp>=3.0` installed but not yet leveraging new features
  (Annotated, Field, ToolError, structured output)

**KG redesign status:**
- Experiment node migration is complete in the KG repo
  (`multiomics_biocypher_kg/docs/experiment_node_migration.md`)
- New schema: Experiment nodes, `Changes_expression_of` edges,
  `Tests_coculture_with`, `Has_experiment`
- Awaiting explorer-side readiness before deploying new KG

---

## Transition phases

### Phase B: Minimal schema migration

Move to the new KG schema with minimal changes. Remove tools that
break, do the minimum to keep remaining tools working. Log what
needs revisiting later — don't try to do everything now.

**Principle:** Get onto the new schema fast. New tools and
improvements come in later phases with skill support.

#### B1: Remove expression tools

Remove `query_expression` and `compare_conditions` — these are
the tools most affected by the schema change (split edge types →
unified `Changes_expression_of`, EnvironmentalCondition → Experiment).
Rebuilding them properly requires summary mode, new parameters,
and new return keys. Do that later with skill support.

**Remove from each layer:**

| Layer | Remove |
|---|---|
| `queries_lib.py` | `build_query_expression`, `build_compare_conditions`, `build_list_condition_types` |
| `api/functions.py` | `query_expression()`, `compare_conditions()` |
| `mcp_server/tools.py` | `query_expression`, `compare_conditions` |
| `__init__.py` | Remove from re-exports |
| Tests | Remove/skip related tests |

**Gate:** All remaining tests pass.

**TODO log** (revisit in later phases):
- [ ] Rebuild `query_expression` with new schema + summary/detail modes (Phase D5)
- [ ] Add `list_experiments` tool (Phase D1)
- [ ] Update `list_filter_values` for treatment_types (Phase D4)
- [ ] `compare_conditions` is permanently removed as a tool.
  The `compare-conditions` pipeline skill (Phase F2) replaces it
  by composing `query_expression` calls for each condition.
- [ ] `get_gene_details` — keep as-is, no schema change needed.
  Consider merging into `gene_overview` in a future phase.

#### B2: Minimal Cypher updates for remaining tools

Update remaining query builders that touch expression-adjacent
parts of the graph. Minimal changes — only what's needed to not
break against the new schema.

| Builder | Change | Notes |
|---|---|---|
| `build_gene_overview` | Update expression count subquery to use `Changes_expression_of` | Minimal — just the edge type name |
| `build_list_filter_values` | Remove condition_types query (EnvironmentalCondition gone) | Return categories only for now |
| Others (resolve_gene, search_genes, get_homologs, ontology tools) | No change expected | These don't touch expression edges |

**Gate:** Unit tests pass with updated Cypher assertions.

#### B3: Deploy new KG

Coordinate with KG repo:
1. Build new KG with Experiment nodes
2. Verify with `validate_connection.py`
3. Run integration tests against new KG
4. Regenerate regression fixtures (`--force-regen`)

**Gate:** All integration and regression tests pass.

#### B4: Update CLAUDE.md

- Remove `query_expression` and `compare_conditions` from tool table
- Note that expression queries are temporarily unavailable,
  being rebuilt with new schema support

---

### Phase C: Dev skills + simple exercises

Build the dev skills, then exercise them on simple tools. Validate
the skills work before using them on complex tools in Phase D.

#### C1: Create dev skills

Create `.claude/skills/` with dev skills:

```
.claude/skills/
├── layer-rules/
│   ├── SKILL.md
│   └── references/layer-boundaries.md
├── add-tool/
│   ├── SKILL.md
│   └── references/checklist.md
├── modify-tool/
│   └── SKILL.md
├── testing/
│   ├── SKILL.md
│   └── references/
│       ├── test-checklist.md
│       └── regression-guide.md
└── code-review/
    ├── SKILL.md
    └── references/review-checklist.md
```

Content from architecture doc dev skill descriptions.

**Gate:** Skills load in Claude Code.

#### C2: Exercise add-tool skill → `list_publications`

Use the `add-tool` skill to add `list_publications` — a new tool
that queries Publication nodes (unchanged by schema migration,
low risk).

Follow the skill's pipeline:
1. Query builder → `build_list_publications()`
2. Unit test
3. API function → `list_publications()`
4. API test
5. MCP wrapper
6. Wrapper test
7. Integration test against live KG
8. Regression cases

**This is a real test of the add-tool skill.** If the skill
misses steps or has wrong conventions, fix the skill.

**Gate:** Tool works end-to-end. Skill is validated or updated.

#### C3: Exercise modify-tool skill → `list_organisms`

Use the `modify-tool` skill to update `list_organisms` — an
existing simple tool. Target changes (pick appropriate ones):
- Leverage FastMCP features (Annotated, Field, annotations)
- Improve docstring for LLM audience
- Update tests

Follow the skill's pipeline:
1. Read current stack
2. Apply changes at each layer
3. Update tests
4. Verify — all tests pass

**Gate:** Tool updated. Skill is validated or updated.

#### C4: Code review + retrospective (round 1)

Run the `code-review` dev skill against C2 and C3 changes:
- Layer boundaries respected?
- Tests cover all layers?
- Naming conventions followed?
- Docstrings match architecture conventions?

Then retrospective on the dev skills themselves: did they guide
correctly? What was missing? What was wrong?

**Update:**
- Dev skills based on what was learned
- Architecture doc if conventions need revision
- Methodology doc if principles need clarification

The dev skills are now validated on simple tools. Phase D
stress-tests them on complex tools while introducing modes.

---

### Phase D: Modes + complex tools

Introduce summary/detail/about modes by building them into
complex tools. This exercises the dev skills on hard problems
while delivering the core v2 architectural change.

#### D1: Add `list_experiments` with modes (add-tool skill)

Use the `add-tool` skill to add `list_experiments` — the first
tool built with summary/detail/about modes from the start.

Complex because:
- Multiple filterable properties (organism, treatment_type,
  omics_type, is_time_course)
- Joins to Publication via `Has_experiment`
- Joins to OrganismTaxon via `Tests_coculture_with` (optional)
- Potentially large result set — needs summary mode

Build the full stack:
1. `build_list_experiments()` — detail query
2. `build_list_experiments_summary()` — aggregation query
3. API function with `summary` + `limit` params
4. MCP tool with `mode` parameter (Annotated, Literal, Field)
5. About-mode content with examples
6. Full test suite including summary consistency

This introduces the mode pattern through a concrete tool, not
as abstract infrastructure.

**Gate:** Tool works with all three modes. Add-tool skill
updated for mode steps.

#### D2: Update `get_homologs` with modes (modify-tool skill)

Use the `modify-tool` skill to update `get_homologs` — the most
complex existing tool (multi-query orchestration, member grouping,
per-group truncation).

Target changes:
- Add summary/detail/about modes
- Leverage FastMCP features (Annotated, Field, ToolError)
- Rename `locus_tag` parameter (cascading rename)
- About-mode content with chaining examples
- Update tests across all layers

This stress-tests the modify-tool skill on cascading changes.

**Gate:** Tool updated with modes. All tests pass.

#### D3: Code review + retrospective (round 2)

Run `code-review` skill against D1 and D2 changes.

**Update:**
- Dev skills — add-tool and modify-tool now cover mode steps,
  complex filtering, multi-query orchestration
- Architecture doc — mode design refined from real experience,
  summary fields per tool, FastMCP patterns
- Methodology doc — principle refinements from building modes
- Code-review skill — was the checklist sufficient for modes?

#### D4: Roll out modes to remaining tools

Apply the mode pattern to remaining tools that need it, using
the now-proven dev skills:
- `search_genes` — summary + detail + about
- `genes_by_ontology` — summary + detail + about
- Other tools — about mode only (small result sets)

**Gate:** All tools have appropriate modes. Unit + integration
tests.

#### D5: Rebuild `query_expression` with new schema

Rebuild `query_expression` properly with the new Experiment
schema, using summary/detail/about modes:
1. `build_query_expression()` — new schema Cypher
2. `build_query_expression_summary()` — aggregation query
3. API function with `summary` + `limit` params
4. MCP tool with three modes
5. About-mode content with examples
6. Full test suite

**Gate:** Expression queries work against new KG. Summary/detail
modes tested.

#### D6: Summary mode consistency tests

Add `test_summary_mode.py`: for each tool with summary mode,
verify summary totals match actual detail row counts.

#### D7: Code review + docs update

Run `code-review` skill against all Phase D changes.

**Update:**
- Architecture doc — finalize mode design, summary fields,
  FastMCP usage patterns
- Methodology doc — any principle refinements
- Dev skills — complete with mode support

---

### Phase E: Precomputed statistics in KG

Coordinate with KG build pipeline to add precomputed summary
statistics to Experiment nodes and other relevant nodes.

#### E1: Define precomputed properties

Decide per tool what to precompute vs aggregate at query time.
Document in each `_summary` builder's docstring.

Candidates for precomputation on Experiment nodes:
- `de_gene_count` (int) — total DE genes
- `direction_breakdown` (JSON str) — {"up": N, "down": M}
- `top_categories` (JSON str) — top functional categories
- `median_log2fc` (float) — median effect size
- `max_log2fc` (float) — max effect size

#### E2: KG build pipeline adds properties

Work in KG repo: add post-import computation step that populates
precomputed properties on Experiment nodes.

#### E3: Update summary builders to use precomputed properties

Update `build_query_expression_summary()` to read from node
properties instead of aggregating. Keep aggregation fallback
for properties not yet precomputed.

**Gate:** Summary mode consistency tests still pass. Summary
queries are faster (verify with timing).

---

### Phase F: Research skills

Build research skills on top of the working summary/detail/about
tools.

#### F1: Layer 1 research skill (multiomics-kg-guide)

Create `multiomics_explorer/skills/multiomics-kg-guide/`:

```
multiomics-kg-guide/
├── SKILL.md                    # Essential rules (~500 tokens)
└── references/
    ├── tool-chaining.md
    ├── summary-vs-detail.md
    ├── mcp-vs-import.md
    └── tools/                  # Per-tool about content (from D4)
        ├── query-expression.md
        ├── search-genes.md
        └── ...
```

The per-tool files already exist from D4 — this step organizes
them into the agentskills.io directory structure.

Set up `scripts/sync_skills.sh` to copy research skills to
`.claude/skills/research/` for dev use.

**Gate:** Skill loads in Claude Code. About mode serves content
from the same files.

#### F2: Layer 2 pipeline skills (draft)

Create draft pipeline skills in `multiomics_explorer/skills/`:
- `characterize-experiment/`
- `gene-survey/`
- `compare-conditions/`
- `export-de-genes/`

These are drafts — refined during Phase 2 stress testing (see
roadmap). Include `SKILL.md` with gated steps, `references/`
for domain guides, `assets/` for analysis templates.

**Gate:** Skills load. Steps reference valid tool names and modes.

#### F3: Layer 3 inversion skill (draft)

Create `clarify-research-question/` with questioning protocol.
Draft — refined during stress testing.

#### F4: MCP server instructions

Update `instructions` parameter in FastMCP with layer 1 content
for chat-mode clients. Same content as the multiomics-kg-guide
SKILL.md, adapted for the MCP instructions format.

---

### Phase G: init-claude and packaging

#### G1: init-claude command

Add `multiomics-explorer init-claude` subcommand to CLI:
- Copies skills from `multiomics_explorer/skills/` to
  `.claude/skills/`
- Creates/updates `.mcp.json` with MCP server config
- Appends KG guidance to `.claude/CLAUDE.md`
- Idempotent

#### G2: Usage logging

Add JSONL logging to MCP tools:
- Tool name, params, mode, duration, result counts
- Skill context field (for connecting calls to workflows)
- Configurable log path, disable via env var

#### G3: Update CLAUDE.md

Update this repo's CLAUDE.md:
- Dual interface (MCP for reasoning, package import for data)
- Layer structure (kg/ → api/ → mcp_server/)
- Tool table updated for new/removed tools
- Skills reference

#### G4: Clean up docs

- Replace old architecture docs with v2 versions
- Remove old transition plan
- Update any stale cross-references

---

## Step dependencies

```
Phase B: Minimal schema migration
  B1 (remove expression tools) → B2 (minimal Cypher updates)
    → B3 (deploy new KG) → B4 (update CLAUDE.md)

Phase C: Dev skills + simple exercises (after B)
  C1 (create dev skills)
    → C2 (add-tool → list_publications)
    → C3 (modify-tool → list_organisms)
    → C4 (review + retrospective, update docs)

Phase D: Modes + complex tools (after C)
  D1 (add-tool → list_experiments with modes)
    → D2 (modify-tool → get_homologs with modes)
    → D3 (review + retrospective, update docs)
    → D4 (roll out modes to remaining tools)
    → D5 (rebuild query_expression)
    → D6 (consistency tests)
    → D7 (review + update docs)

Phase E: Precomputed stats (after D)
  E1 (define) → E2 (KG pipeline) → E3 (update builders)

Phase F: Research skills (after D)
  F1 (layer 1) — after D (about content exists from D1-D4)
  F2 (layer 2 drafts) — independent
  F3 (layer 3 draft) — independent
  F4 (MCP instructions) — after F1

Phase G: Packaging (after F)
  G1 (init-claude) — after F1, F2, F3
  G2 (usage logging) — independent
  G3 (CLAUDE.md) — after D
  G4 (docs cleanup) — last
```

**Parallelism opportunities:**
- About-mode content writing can happen alongside mode
  implementation, but D4 (roll out modes) depends on D1-D3
- E1-E2 (precomputed stats) can overlap with D if summary
  builders start with aggregation and switch to precomputed
  properties when available
- F2-F3 (pipeline/inversion skill drafts) can be drafted during
  D but require D for validation of tool/mode references
- G2 (usage logging) is independent of everything else

---

## Coordinated work with KG repo

| This repo | KG repo | When |
|---|---|---|
| B1-B2: Remove expression tools, minimal Cypher fixes | Deploy Experiment node KG | B3: coordinate deployment |
| D1: Define summary queries | — | No KG change needed if using aggregation |
| E1: Define precomputed properties | E2: Add computation to build pipeline | Coordinate property names + types |
| — | Rebuild KG with precomputed stats | E3: update summary builders |

The KG Experiment node migration is ready in the KG repo. The
explorer needs to complete B1-B2 before the new KG can be deployed
(B3).

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| B1 (removing expression tools) breaks user workflows | Temporarily no expression queries | Minimal downtime — rebuild in D5 with proper modes. Document in CLAUDE.md. |
| Dev skills are wrong or incomplete | Claude builds tools incorrectly | C2-C3 exercise skills on real tools. C4 retrospective fixes issues before building more. |
| Summary queries return different totals than detail | Data integrity issue | D6 consistency tests. Run after every schema or query change. |
| Precomputed stats drift from actual data | Summary mode returns wrong counts | D6 consistency tests. Regenerate precomputed stats on every KG rebuild. |
| About content drifts from tool behavior | Claude learns wrong patterns | Structured format with `expected-keys` blocks tested against `EXPECTED_KEYS`. |
| Skills are too prescriptive / not prescriptive enough | Claude follows wrong workflow or ignores skills | Phase 2 stress testing refines skills before shipping to researchers. |
| FastMCP 3.x breaking changes | Tools stop working | Pin to `fastmcp>=3.0,<4.0`. Run tests on upgrade. |
