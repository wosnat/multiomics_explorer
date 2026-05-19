# Metabolites Assets + Surface Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce three metabolites artifacts — a quantified-and-prioritised audit doc (5 parts), an LLM-targeted analysis doc registered as `docs://analysis/metabolites`, and a runnable example python registered as `docs://examples/metabolites.py` covering eight scenarios across the three Metabolite-source pipelines (transport / gene reaction / metabolomics).

**Architecture:** Two-pass audit loop with the analysis doc and example python sandwiched between passes. First pass populates audit Parts 2/3a/3b/5 with obvious items (`phase=first-pass`); building the analysis doc and example python surfaces refinements and build-derived items; second pass appends them (`phase=build-derived`). All artifacts treat the three Metabolite-source pipelines as first-class with caveats per source.

**Tech Stack:** Markdown for the audit + analysis doc; Python 3.13 + the `multiomics_explorer` package (`run_cypher`, `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`, `differential_expression_by_gene`, `genes_by_function`, `search_ontology`) for the example; FastMCP for static resource registration; pytest under `-m kg` for the smoke test.

**Spec:** [`docs/superpowers/specs/2026-05-04-metabolites-assets-design.md`](../specs/2026-05-04-metabolites-assets-design.md) (commit 88308a7).

**Branch / worktree:** Author the plan against `main`. Execution may run on `main` or in a dedicated worktree (decided at execution-mode handoff). All commits land directly on the working branch.

**MCP restart reminder:** After any change to `multiomics_explorer/mcp_server/server.py`, the user must `/mcp` restart before MCP tool calls reflect the change. Tasks that require restart say so explicitly.

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` | Create | The 5-part audit doc (KG inventory + Parts 2/3a/3b/4/5). Two-pass: first pass before doc/example, second pass after. |
| `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` | Create | LLM-targeted analysis doc, three-source disambiguation table + tracks A1/A2/A-combined/B. Auto-registered as `docs://analysis/metabolites` by the loop in `multiomics_explorer/mcp_server/server.py:71-86`. |
| `examples/metabolites.py` | Create | Runnable script with 8 scenarios + `--scenario` CLI. Will be registered statically in `server.py`. |
| `examples/README.md` | Modify | Document the new script alongside `pathway_enrichment.py`. |
| `multiomics_explorer/mcp_server/server.py` | Modify (one block, lines 88-99 area) | Add static `add_resource` call for `docs://examples/metabolites.py`. |
| `tests/integration/test_examples.py` | Modify | Add a parametrised smoke test mirroring the existing `pathway_enrichment` test, exercising every scenario under `-m kg`. |

No changes are needed to `inputs/tools/*.yaml`, `mcp_server/tools.py` Pydantic models, or `scripts/build_about_content.py` — analysis docs are hand-authored, no new MCP tools are introduced.

---

## Phase A — Audit doc skeleton + Part 1 (KG inventory)

### Task A1: Audit doc skeleton + Part 1 KG inventory

**Files:**
- Create: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md`

- [ ] **Step 1: Create the audit-doc skeleton.**

Write the following file:

```markdown
# Metabolites Surface Audit — 2026-05-04

**Date:** 2026-05-04
**Spec:** [2026-05-04-metabolites-assets-design.md](2026-05-04-metabolites-assets-design.md)
**Owner:** Osnat Weissberg
**Status:** First pass in progress

This audit accompanies the metabolites assets effort. It quantifies the metabolite surface in the KG, lists existing-tool gaps for both chemistry-annotation and metabolomics-measurement layers, proposes new tools, captures open definition questions, and itemises KG-side asks. The audit runs in two passes: a first pass populated before the analysis doc and example python are written (`phase=first-pass`), and a second pass appended after they are written (`phase=build-derived`).

## Part 1 — KG inventory (quantified)

All counts come from live `run_cypher` queries against the deployed KG. Each query is shown inline; numbers are reported as of the audit date.

### 1.1 Source-coverage Venn over Metabolite

(populated by Step 2)

### 1.2 Per-source edge inventory

(populated by Step 3)

### 1.3 Transport (TCDB) source

(populated by Step 4)

### 1.4 Reaction (KEGG) source

(populated by Step 5)

### 1.5 Metabolomics measurement source

(populated by Step 6)

## Part 2 — Chemistry-annotation surface (existing tools)

(first pass — Phase B Task B1; second pass — Phase E Task E1)

| Tool | Current chemistry surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|

## Part 3 — Metabolomics-measurement surface (greenfield)

### 3a — Existing-tool modifications

(first pass — Phase B Task B2; second pass — Phase E Task E2)

| Tool | Current surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|

### 3b — New-tool proposals

(first pass — Phase B Task B3; second pass — Phase E Task E3)

## Part 4 — Open definition questions

(populated — Phase B Task B4)

## Part 5 — KG-side asks

(first pass — Phase B Task B5; second pass — Phase E Task E4)

| ID | Category | Priority | Phase | Ask | Why (explorer item it unblocks) |
|---|---|---|---|---|---|
```

- [ ] **Step 2: Run the source-coverage Venn query.**

Run via `mcp__multiomics-kg__run_cypher` (or `uv run multiomics-explorer cypher` if MCP is unavailable):

```cypher
MATCH (m:Metabolite)
WITH m,
     EXISTS((m)<-[:Tcdb_family_substrate_metabolite]-(:TcdbFamily)) AS has_transport,
     EXISTS((m)<-[:Reaction_involves_metabolite]-(:Reaction)) AS has_reaction,
     EXISTS((m)<-[:Assay_quantifies_metabolite|Assay_flags_metabolite]-(:MetaboliteAssay)) AS has_measurement
RETURN
  CASE WHEN has_transport AND has_reaction AND has_measurement THEN 'transport+reaction+measurement'
       WHEN has_transport AND has_reaction THEN 'transport+reaction'
       WHEN has_transport AND has_measurement THEN 'transport+measurement'
       WHEN has_reaction AND has_measurement THEN 'reaction+measurement'
       WHEN has_transport THEN 'transport-only'
       WHEN has_reaction THEN 'reaction-only'
       WHEN has_measurement THEN 'measurement-only'
       ELSE 'orphan' END AS bucket,
  count(m) AS n
ORDER BY n DESC;
```

Note: edge label names are inferred from `kg_schema` and the chemistry slice-1 docs. If the actual labels differ, run `kg_schema` first and adjust before executing the Venn query.

Record the result table verbatim into §1.1 of the audit, plus a one-sentence summary (e.g., "10/X metabolites are measurement-only — i.e., no chemistry annotation").

Also run:

```cypher
MATCH (m:Metabolite)
RETURN coalesce(m.compartment, '<missing>') AS compartment, count(*) AS n
ORDER BY n DESC;
```

Record this as the by-compartment breakdown in §1.1.

- [ ] **Step 3: Run the per-source edge inventory.**

For each of the three source paths, run a `kg_schema`-style introspection to enumerate edge labels and edge-level properties:

```cypher
// Transport: Gene -> TcdbFamily -> Metabolite
MATCH (g:Gene)-[r1]->(f:TcdbFamily)
WITH labels(g) AS gl, type(r1) AS rt1, keys(r1) AS rk1, labels(f) AS fl
RETURN rt1 AS edge, rk1 AS edge_props, count(*) AS n
ORDER BY n DESC LIMIT 5;

MATCH (f:TcdbFamily)-[r2]->(m:Metabolite)
RETURN type(r2) AS edge, keys(r2) AS edge_props, count(*) AS n
ORDER BY n DESC LIMIT 5;

// Reaction: Gene -> Reaction -> Metabolite
MATCH (g:Gene)-[r1]->(rx:Reaction)
RETURN type(r1) AS edge, keys(r1) AS edge_props, count(*) AS n
ORDER BY n DESC LIMIT 5;

MATCH (rx:Reaction)-[r2]->(m:Metabolite)
RETURN type(r2) AS edge, keys(r2) AS edge_props, count(*) AS n
ORDER BY n DESC LIMIT 5;

// Measurement: MetaboliteAssay -> Metabolite
MATCH (a:MetaboliteAssay)-[r]->(m:Metabolite)
RETURN type(r) AS edge, keys(r) AS edge_props, count(*) AS n
ORDER BY n DESC LIMIT 5;
```

Record results in §1.2. For each `edge_props` list that is empty or surprisingly thin (e.g., no replicate/normalisation property on Assay edges), add a one-line note flagging the gap; these notes feed Part 4 (open questions) and Part 5 (KG asks).

- [ ] **Step 4: Run transport-source counts.**

```cypher
MATCH (f:TcdbFamily) RETURN count(f) AS tcdb_family_count;

MATCH (g:Gene)-[r:Gene_belongs_to_tcdb_family]->(f:TcdbFamily)
RETURN count(*) AS gene_family_edges,
       count(DISTINCT g) AS distinct_genes_with_family,
       count(DISTINCT f) AS distinct_families_with_genes;

MATCH (f:TcdbFamily)-[r:Tcdb_family_substrate_metabolite]->(m:Metabolite)
RETURN count(*) AS family_metabolite_edges,
       count(DISTINCT f) AS distinct_families_with_substrates,
       count(DISTINCT m) AS distinct_metabolites_with_transport;

// substrate_confirmed vs family_inferred split
MATCH (g:Gene)-[:Gene_belongs_to_tcdb_family]->(f:TcdbFamily)-[r:Tcdb_family_substrate_metabolite]->(m:Metabolite)
WITH g, m, collect(coalesce(r.confidence, 'family_inferred')) AS confs
RETURN
  CASE WHEN 'substrate_confirmed' IN confs THEN 'substrate_confirmed'
       ELSE 'family_inferred' END AS tier,
  count(*) AS gene_metabolite_pairs;
```

(The exact edge label and confidence property may differ — adjust per Step 3's output. The intent is: total counts at each tier.)

Record in §1.3.

- [ ] **Step 5: Run reaction-source counts.**

```cypher
MATCH (rx:Reaction) RETURN count(rx) AS reaction_count;

MATCH (g:Gene)-[:Gene_catalyses_reaction]->(rx:Reaction)
RETURN count(*) AS gene_reaction_edges,
       count(DISTINCT g) AS distinct_genes,
       count(DISTINCT rx) AS distinct_reactions;

MATCH (rx:Reaction)-[:Reaction_involves_metabolite]->(m:Metabolite)
RETURN count(*) AS reaction_metabolite_edges,
       count(DISTINCT rx) AS distinct_reactions,
       count(DISTINCT m) AS distinct_metabolites_with_reaction;

// Distribution: reactions per gene, metabolites per reaction
MATCH (g:Gene)-[:Gene_catalyses_reaction]->(rx:Reaction)
WITH g, count(rx) AS rx_per_gene
RETURN min(rx_per_gene) AS rx_min, percentileDisc(rx_per_gene, 0.5) AS rx_median, max(rx_per_gene) AS rx_max;

MATCH (rx:Reaction)-[:Reaction_involves_metabolite]->(m:Metabolite)
WITH rx, count(m) AS m_per_rx
RETURN min(m_per_rx) AS m_min, percentileDisc(m_per_rx, 0.5) AS m_median, max(m_per_rx) AS m_max;
```

Record in §1.4.

- [ ] **Step 6: Run measurement-source counts.**

```cypher
MATCH (a:MetaboliteAssay) RETURN count(a) AS assay_count;

MATCH (e:Experiment)-[:Experiment_has_assay|Has_metabolite_assay]->(a:MetaboliteAssay)
RETURN count(*) AS assay_experiment_edges,
       count(DISTINCT e) AS distinct_experiments_with_assays;

MATCH (p:Publication)<-[:Reported_in|From_publication]-(:Experiment)-[]->(a:MetaboliteAssay)
RETURN count(DISTINCT p) AS publications_with_metabolomics, collect(DISTINCT p.doi)[..5] AS sample_dois;

// quantified vs flagged split
MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(:Metabolite)
RETURN count(*) AS quantifies_edges, count(DISTINCT a) AS assays_with_quantifies;

MATCH (a:MetaboliteAssay)-[r:Assay_flags_metabolite]->(:Metabolite)
RETURN count(*) AS flags_edges, count(DISTINCT a) AS assays_with_flags;

// per-organism, per-growth_phase, per-treatment_type, per-compartment coverage
MATCH (o:Organism)<-[:Profiles]-(:Experiment)-[]->(a:MetaboliteAssay)
RETURN o.preferred_name AS organism, count(DISTINCT a) AS assays
ORDER BY assays DESC;

MATCH (e:Experiment)-[]->(a:MetaboliteAssay)
RETURN coalesce(e.background_factors, []) AS bg_factors, count(DISTINCT a) AS assays
ORDER BY assays DESC;

MATCH (a:MetaboliteAssay)-[]->(m:Metabolite)
RETURN coalesce(m.compartment, '<missing>') AS compartment, count(DISTINCT m) AS metabolites
ORDER BY metabolites DESC;
```

(Edge labels for `Experiment-MetaboliteAssay` and `Experiment-Organism` are inferred from `kg_schema`; adjust if Step 3's introspection reveals different names. Also: `Profiles` is illustrative — use the real organism-experiment label.)

Record in §1.5. Add a one-sentence summary noting how many of the +10 measurement-only metabolites are extracellular (per the commit message in `b83b7f9`, all should be).

- [ ] **Step 7: Commit Phase A.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "$(cat <<'EOF'
audit(metabolites): Part 1 — KG inventory quantified

Source-coverage Venn over Metabolite, per-source edge inventory,
transport/reaction/measurement counts pulled live from KG.
Sets up Parts 2-5 first pass.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase B — Audit first pass (Parts 2, 3a, 3b, 4, 5)

### Task B1: Part 2 first pass — chemistry-annotation surface

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 2 table)

- [ ] **Step 1: Read the current state of each candidate tool.**

For each tool below, look at its YAML (`multiomics_explorer/inputs/tools/{tool}.yaml`) and Pydantic envelope/row models in `multiomics_explorer/mcp_server/tools.py`. Note whether the tool currently surfaces any of: `reaction_count`, `metabolite_count`, `transporter_count`, ontology routing to TCDB, chemistry-pathway distinction, or related.

Tools to evaluate:
- Already-surfacing-something: `gene_overview`, `list_organisms`, `genes_by_ontology` (TCDB chain), `pathway_enrichment` (KEGG)
- Likely gaps: `gene_details`, `gene_response_profile`, `differential_expression_by_gene`, `differential_expression_by_ortholog`, `gene_homologs`, `genes_by_homolog_group`, `search_homolog_groups`, `gene_clusters_by_gene`, `genes_in_cluster`, `list_clustering_analyses`, `gene_derived_metrics`, `genes_by_numeric_metric`, `genes_by_boolean_metric`, `genes_by_categorical_metric`, `list_derived_metrics`, `list_publications`, `list_experiments`, `list_filter_values`, `genes_by_function`, `gene_ontology_terms`, `kg_schema`, `cluster_enrichment`, `resolve_gene`, `run_cypher`.

- [ ] **Step 2: Populate Part 2 table.**

Add one row per tool to `## Part 2` in the audit doc. Required columns: Tool, Current chemistry surfacing, Recommended change, Priority (P0/P1/P2/P3), Phase (`first-pass`).

Guidance on assigning priority:
- **P0** = the LLM will give wrong answers without this. Example: `gene_response_profile` not surfacing chemistry rollups means the LLM doesn't know whether to drill into chemistry on a noteworthy gene.
- **P1** = significant coverage gain but LLM can route via other tools today.
- **P2** = polish (e.g., adding a hint string).
- **P3** = defer.

For tools that already surface chemistry well (e.g., `gene_overview`), the recommended-change cell should explicitly say "no change" rather than being omitted.

Sort the table: P0 first, then P1, then P2, then P3.

- [ ] **Step 3: Sanity check coverage.**

Re-read the §1 caveats list in the spec. For each caveat (family_inferred dominance, KO-inference putative, no-gene-anchor, etc.), confirm there is at least one Part 2 row that addresses how an existing tool either does or doesn't help the LLM apply that caveat. If a caveat has no row, add one or note it as "covered by Part 3b new tool" in the cell.

- [ ] **Step 4: Commit Part 2 first pass.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "$(cat <<'EOF'
audit(metabolites): Part 2 first pass — chemistry-annotation gaps

Per-tool table: 28 tools evaluated; gaps prioritised P0-P3.
Phase=first-pass; build-derived rows added in second pass after
the analysis doc and example python expose additional gaps.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B2: Part 3a first pass — measurement-surface existing-tool mods

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 3a table)

- [ ] **Step 1: Identify candidate tools and their measurement-surfacing gaps.**

Check each tool below against measurement-side data (MetaboliteAssay, omics_type=METABOLOMICS, extracellular compartment):
- `list_metabolites` — does it have `measured_in_experiments` or per-row `assay_count` / `quantified_in` / `flagged_in`? (Likely no — the gap is rich.)
- `list_publications` — does it surface MetaboliteAssay counts per row when omics_type includes METABOLOMICS?
- `list_experiments` — same.
- `list_organisms` — does the `by_metabolic_capability` rollup include measurement coverage?
- `kg_schema` — does the new node/edge inventory appear?
- `list_filter_values` — does the compartment filter include `extracellular`?

- [ ] **Step 2: Populate Part 3a table.**

Same column shape as Part 2: Tool, Current surfacing, Recommended change, Priority, Phase=`first-pass`.

P0 candidates here: anything that would make the LLM unable to *find* metabolomics experiments (e.g., `list_publications` not surfacing the new papers' metabolomics nature). P1: rich-rollup additions to `list_metabolites`.

- [ ] **Step 3: Commit Part 3a first pass.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "audit(metabolites): Part 3a first pass — measurement-side existing-tool mods

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B3: Part 3b first pass — new-tool proposals

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 3b)

- [ ] **Step 1: Write each first-pass proposal.**

For each candidate listed below, write one paragraph + signature sketch + `{recommendation, phase}`. Recommendation: Must-add / Should-add / Nice-to-have / Pending-definition / Not-needed. Phase=`first-pass`. Each Pending-definition entry must name its blocking Part 4 question(s).

First-pass candidates (justified by structural analysis, not by the build):

- **`list_metabolite_assays`** — discovery surface mirroring `list_experiments` but per-MetaboliteAssay. Filterable by organism / treatment_type / background_factors / publication / metabolite IDs / compartment. Returns per-row metabolite counts and routing hints. Justification: structural — there's a node type with no discovery tool. Recommendation: **Should-add** (P1). Not Must-add because users can find metabolomics experiments via `list_experiments(omics_types=['METABOLOMICS'])` today, but the per-assay grain is missing.
- **`metabolite_response_profile`** — cross-experiment per-metabolite summary mirroring `gene_response_profile`. Inputs: metabolite IDs + organism. Output: per-metabolite breadth/rank/value stats. Recommendation: **Pending-definition** (depends on Part 4: replicate rollup, FC-vs-other-statistic).
- **`metabolites_by_assay`** / **`assays_by_metabolite`** — drill-down pair (assay → metabolites; metabolite → assays). Recommendation: **Should-add** (P1). Mostly mechanical given `list_metabolite_assays` exists.
- **`differential_metabolite_abundance`** — DE-shaped tool. Recommendation: **Pending-definition** (depends on Part 4: FC relevance, replicate rollup, normalisation).
- **DM-family extension to Metabolite entity** — adding `Metabolite` as a target alongside `Gene` for `list_derived_metrics`, `gene_derived_metrics`, `genes_by_*_metric`. Recommendation: **Pending-definition** (depends on Part 4: is metabolomics modelled as DM on Metabolite or first-class Assay surface?).

- [ ] **Step 2: Verify Pending-definition cross-references.**

Each Pending-definition entry must literally name the Part 4 question (e.g., "Pending Part 4: FC relevance for metabolomics"). Re-read the Part 4 plan (Task B4) to ensure the blocking questions exist there.

- [ ] **Step 3: Commit Part 3b first pass.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "audit(metabolites): Part 3b first pass — new-tool proposals

5 first-pass candidates: list_metabolite_assays (Should-add),
metabolite_response_profile (Pending-definition),
metabolites_by_assay/assays_by_metabolite (Should-add),
differential_metabolite_abundance (Pending-definition),
DM-family extension to Metabolite (Pending-definition).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B4: Part 4 — open definition questions

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 4)

- [ ] **Step 1: Write Part 4 grouped by source pipeline.**

Write the questions verbatim from the spec §3.1 Part 4 (already grouped by source). For each question, expand into:
- **Question:** (one sentence)
- **Why it matters:** (one sentence — what depends on the answer)
- **Options the user might consider:** (bullet list, only when the option space is enumerable)
- **Blocks:** (named Part 3b proposals or KG asks that depend on this answer)

Reaction (KEGG) source: 3 questions (directionality, reversibility, multi-subunit attribution).
Transport (TCDB) source: 2 questions (direction, primary-substrate property).
Metabolomics measurement source: 7 questions (DM-vs-Assay surface, FC relevance, replicate rollup, Quantifies-vs-Flags semantics, compartment semantics, replicate/temporal axis, cross-organism comparability).

- [ ] **Step 2: Cross-link from Part 3b.**

Re-read the Pending-definition entries written in Task B3. Update each to literally point at the Part 4 question (e.g., "Blocks: `differential_metabolite_abundance`, `metabolite_response_profile`"). Conversely, each Part 4 entry's Blocks line should name the Part 3b proposals that depend on it.

- [ ] **Step 3: Commit Part 4.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "audit(metabolites): Part 4 — open definition questions grouped by source

12 questions (3 reaction, 2 transport, 7 measurement); each names
the Part 3b proposals it blocks. Cross-links closed both ways.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task B5: Part 5 first pass — KG-side asks

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 5 table + body)

- [ ] **Step 1: Write category and priority definitions.**

Copy the category and priority definitions from spec §3.1 Part 5 verbatim into the audit doc (so the audit is self-contained without requiring readers to chase the design).

- [ ] **Step 2: Populate Part 5 table.**

For each first-pass candidate ask, fill in `{ID, category, priority, phase=first-pass, ask, why}`. ID format: `KG-MET-001`, `KG-MET-002`, ... (`MET` prefix to distinguish from prior `kg-side-*-asks` docs).

First-pass asks (initial set, audit phase will refine):

| ID | Category | Priority | Phase | Ask | Why |
|---|---|---|---|---|---|
| KG-MET-001 | Data gap | P1 | first-pass | Add `replicate_count`, `normalisation_method`, `is_processed_value` properties on `Assay_quantifies_metabolite` and `Assay_flags_metabolite` edges | Unblocks measurement-track tools (`metabolite_response_profile`, `differential_metabolite_abundance`); resolves Part 4 replicate-rollup question |
| KG-MET-002 | Schema + Decision | P0 | first-pass | Decide compartment-as-property vs compartment-as-distinct-node, document and apply consistently | Affects every chemistry tool's compartment filter and the measurement track's extracellular semantics; resolves Part 4 compartment question |
| KG-MET-003 | Data gap or Schema | P1 | first-pass | Reaction edge directionality / role (substrate vs product) | Affects `metabolites_by_gene` honesty (whether "this gene produces X" claim is supportable); resolves Part 4 reaction-direction question |
| KG-MET-004 | Rollup | P2 | first-pass | Per-Metabolite measurement rollups (`assay_count`, `experiments_measured_in`, `quantified_in_count`, `flagged_in_count`) materialised on the Metabolite node | Enables `list_metabolites` to surface measurement coverage without query-time traversal |
| KG-MET-005 | Rollup | P2 | first-pass | Per-Publication and per-Experiment metabolomics-capability rollups (`metabolite_assay_count`, `distinct_metabolites_measured`) materialised on those nodes | Enables `list_publications` / `list_experiments` to surface measurement-capability without traversal |
| KG-MET-006 | Precompute | P2 | first-pass | TCDB family promiscuity precompute (`is_superfamily` boolean or `substrate_count_percentile`) on TcdbFamily nodes | Enables `metabolites_by_gene` and `genes_by_metabolite` to dim/rank family_inferred rows that come from promiscuous families |
| KG-MET-007 | Index | P2 | first-pass | (Defer specific entries until proposed-tool signatures stabilise; insert as build-derived in second pass) | Performance for new query paths |
| KG-MET-008 | Documentation | P3 | first-pass | Document the metabolomics-extension data dictionary (paper provenance, normalisation conventions per paper, growth_phase encoding) | LLM-readable provenance; not strictly blocking but reduces ambiguity |

- [ ] **Step 3: Commit Part 5 first pass.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "audit(metabolites): Part 5 first pass — KG-side asks (KG-MET-001..008)

7 substantive asks + 1 deferred (KG-MET-007 indexes — populated
in second pass once proposed-tool signatures stabilise).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase C — Analysis doc

### Task C1: Analysis doc skeleton + disambiguation table

**Files:**
- Create: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md`

- [ ] **Step 1: Read peer analysis docs for style.**

Read `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md` (and `derived_metrics.md` if shorter) to internalise the LLM-facing terse decision-tree style. The metabolites doc should match.

- [ ] **Step 2: Write skeleton + disambiguation table.**

```markdown
# Working with metabolites

This guide is for LLM consumers. The KG models metabolites via three distinct source pipelines, each answering a different question class. Read the table below first; pick the right row before drilling.

## Source disambiguation

| `evidence_source` | Path | Question it answers | Native tools | Key caveats |
|---|---|---|---|---|
| `metabolism` | `Gene → Reaction → Metabolite` (KEGG) | Which metabolites can this gene catalyse? | `genes_by_metabolite`, `metabolites_by_gene` | KO inference may be putative; reaction direction modelling unresolved (see audit Part 4); promiscuous enzymes inflate counts |
| `transport` | `Gene → TcdbFamily → Metabolite` (TCDB) | Which metabolites does this gene transport (or could transport, family-inferred)? | `genes_by_metabolite`, `metabolites_by_gene` | family_inferred ≫ substrate_confirmed; ABC superfamily promiscuity (auto-warning); no import/export direction |
| `metabolomics` | `MetaboliteAssay → Metabolite` (mass-spec) | Which metabolites were measured under this condition? | None native today; use `run_cypher` (banner below) | No gene anchor; detection vs quantification semantics differ; compartment matters; targeted panel ≠ full metabolome |

The first two rows share tools (the `evidence_source` field on `genes_by_metabolite` / `metabolites_by_gene` rows is the discriminator). The third row has no native tool — see Track B.

## Tracks

(populated in Tasks C2-C5)

- **Track A1 — Reaction (KEGG) annotation**
- **Track A2 — Transport (TCDB) annotation**
- **Track A — Combined annotation workflows** (cross-arm and downstream)
- **Track B — Metabolomics measurement** (partially tooled)
```

- [ ] **Step 3: Commit skeleton.**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
git commit -m "docs(analysis): metabolites skeleton + source-disambiguation table

Three-row table keyed on evidence_source (metabolism / transport /
metabolomics). LLM reads this first to route correctly between
the three Metabolite-source pipelines.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C2: Track A1 — Reaction (KEGG) annotation

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md`

- [ ] **Step 1: Append Track A1 section.**

Append the following section, replacing the placeholder bullet `- **Track A1 — Reaction (KEGG) annotation**`:

```markdown
## Track A1 — Reaction (KEGG) annotation

Use when the question is about chemistry the gene can catalyse via curated KEGG enzyme reactions.

**Caveats** (always apply — restate them inline if surfacing results to the user):
- KO inference may be putative; many bacterial reaction annotations are sequence-homology-based.
- Reaction direction modelling is open (audit Part 4) — prefer "involved in" framing over "produces" / "consumes" until resolved.
- Promiscuous enzymes inflate metabolite counts.

### a — Metabolite discovery & filtering

**Tool:** `list_metabolites`

**When:** "what metabolites does the KG know about, filtered by element / mass / pathway / xref / organism" — discovery before downstream drill-down.

**Pattern:**
```python
result = list_metabolites(
    elements=["N"],            # presence-only AND-of
    pathway_ids=["map00910"],  # nitrogen metabolism
    organism="MED4",
    limit=20,
)
# Read result["top_pathways"], result["top_organisms"], result["xref_coverage"]
```

### b1 — Reaction-anchored: compound → genes

**Tool:** `genes_by_metabolite` with `evidence_sources=["metabolism"]`.

**When:** "which MED4 genes catalyse a reaction involving glucose?"

**Pattern:**
```python
result = genes_by_metabolite(
    metabolite_ids=["C00031"],
    organism="MED4",
    evidence_sources=["metabolism"],
)
# Each row has evidence_source="metabolism" and an EC number / reaction_id.
```

### c1 — Reaction-anchored: gene → metabolites

**Tool:** `metabolites_by_gene` with `evidence_sources=["metabolism"]`.

**When:** "which metabolites does PMM0001 catalyse reactions involving?"

**Pattern:**
```python
result = metabolites_by_gene(
    locus_tags=["PMM0001"],
    organism="MED4",
    evidence_sources=["metabolism"],
)
# Read result["by_element"] (chemistry signature) and result["top_pathways"]
# (chemistry-pathway distinction — see "ontology bridges" caveat below).
```

**Caveat — `top_pathways` ≠ KEGG-KO pathways from `genes_by_ontology`.** The chemistry-side `top_pathways` walks Reaction → KeggPathway via reaction-pathway edges (filtered to `KeggTerm.reaction_count >= 3`). This is distinct from gene-KO pathway annotations from `genes_by_ontology(ontology="kegg")`. If the user wants the KO pathway annotation surface, route to that tool instead.
```

- [ ] **Step 2: Commit Track A1.**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
git commit -m "docs(analysis): metabolites Track A1 — reaction annotation workflows (a/b1/c1)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C3: Track A2 — Transport (TCDB) annotation

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md`

- [ ] **Step 1: Append Track A2 section.**

```markdown
## Track A2 — Transport (TCDB) annotation

Use when the question is about substrates the gene's TCDB family transports.

**Caveats:**
- family_inferred ≫ substrate_confirmed — most rows are inherited from family-level curation, not gene-specific evidence.
- ABC superfamily is especially promiscuous: 9 MED4 ABC genes × ~551 substrates each. The family_inferred-dominance auto-warning fires when this skews a result.
- Import vs export direction is not represented.

### b2 — Transport-anchored: compound → genes

**Tool:** `genes_by_metabolite` with `evidence_sources=["transport"]`.

**When:** "which MED4 genes are predicted to transport glycine betaine?"

**Pattern:**
```python
result = genes_by_metabolite(
    metabolite_ids=["C00719"],
    organism="MED4",
    evidence_sources=["transport"],
    transport_confidence="substrate_confirmed",  # tighten if family_inferred dominates
)
# Each row has evidence_source="transport" and transport_confidence ∈ {substrate_confirmed, family_inferred}.
```

### c2 — Transport-anchored: gene → metabolites

**Tool:** `metabolites_by_gene` with `evidence_sources=["transport"]`.

**When:** "what does this gene's TCDB family transport?"

**Pattern:**
```python
result = metabolites_by_gene(
    locus_tags=["PMM0001"],
    organism="MED4",
    evidence_sources=["transport"],
)
# Detail rows are sorted by precision tier — substrate_confirmed first, then family_inferred.
```

### g — Precision-tier reading

When the auto-warning fires (`family_inferred dominance`), it means most rows came from broad family-level inheritance rather than gene-level evidence. Strategies:
- Tighten with `transport_confidence="substrate_confirmed"` if the user wants high-confidence rows only.
- Read the warning text to find the dominant family (often ABC superfamily) and decide whether to filter it out via `tcdb_family_ids` exclusion.
- For drill-downs into a single transporter family, use `genes_by_ontology(ontology="tcdb", term_ids=[...])`.
```

- [ ] **Step 2: Commit Track A2.**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
git commit -m "docs(analysis): metabolites Track A2 — transport annotation workflows (b2/c2/g)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C4: Track A combined — cross-arm workflows

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md`

- [ ] **Step 1: Append Track A combined section.**

```markdown
## Track A — Combined annotation workflows

Workflows that cross both reaction and transport arms, or that consume the annotation-side results downstream.

### d — Cross-feeding bridge (Workflow B′)

**When:** "what could MED4 produce that ALT might consume?" — between-organism metabolic coupling.

**Pattern (two-step):**
```python
# 1. Harvest MED4-side metabolite IDs from gene-anchored chemistry.
med4_chem = metabolites_by_gene(
    locus_tags=["PMM0001", "PMM0002", ...],
    organism="MED4",
    summary=True,
)
metabolite_ids = [m["metabolite_id"] for m in med4_chem["top_metabolites"]]

# 2. Cross to ALT — which ALT genes can metabolise / transport those?
alt_consumers = genes_by_metabolite(
    metabolite_ids=metabolite_ids,
    organism="ALT_MACL",
)
```

**Caveat:** the KG is annotation-only — direction of cross-feeding (which organism actually produces vs consumes under what condition) is not represented. The Track-B measurement layer can corroborate but not confirm causality.

### e — N-source / nutrient-class workflow

**When:** "which MED4 genes act on nitrogen-containing metabolites — and which of those respond to N starvation?"

**Pattern (2-3 steps):**
```python
# 1. N-bearing chemistry-side gene set.
chem = metabolites_by_gene(
    locus_tags=[...],
    organism="MED4",
    metabolite_elements=["N"],
    summary=True,
)
locus_tags = [g["locus_tag"] for g in chem["top_genes"]]

# 2. DE under N starvation.
de = differential_expression_by_gene(
    organism="MED4",
    locus_tags=locus_tags,
    direction="both",
    significant_only=True,
)
```

**Caveat:** promiscuous enzymes / family_inferred transport inflate the gene set fed to DE. Tighten via `evidence_sources=["metabolism"]` and/or `transport_confidence="substrate_confirmed"` if the result is noisy.

### f — Ontology bridges

**TCDB substrate-anchored:** to find genes annotated to a transporter family that handles a specific substrate, prefer the metabolite-anchored route — `genes_by_metabolite(metabolite_ids=[...], organism=...)` with `evidence_sources=["transport"]` — over `genes_by_ontology(ontology="tcdb", ...)`. The metabolite-anchored route includes all families curating the substrate; the ontology route is family-anchored and misses cross-family substrate hits.

**KEGG pathway-anchored:** for chemistry-pathway discovery (which metabolites are in pathway X), use `list_metabolites(pathway_ids=[...])`. For gene-KO pathway annotations (which genes are annotated to KO terms in pathway X), use `genes_by_ontology(ontology="kegg", ...)`. They are different surfaces — call out the distinction when answering.
```

- [ ] **Step 2: Commit Track A combined.**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
git commit -m "docs(analysis): metabolites Track A combined — d/e/f cross-arm workflows

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task C5: Track B — measurement, plus resource-registration verification

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md`

- [ ] **Step 1: Append Track B section.**

```markdown
## Track B — Metabolomics measurement (partially tooled)

> **Native tools pending.** No MCP tool surfaces `MetaboliteAssay` data today. Use `run_cypher` patterns below until the metabolomics-DM tool ships. See [audit](../../../../docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md) for the planned surface.

**Caveats** (always restate when surfacing results):
- **No gene anchor.** A metabolite measurement says nothing about which gene produced/consumed it.
- **`Assay_quantifies` vs `Assay_flags`.** `Assay_quantifies_metabolite` carries quantitative concentration / intensity; `Assay_flags_metabolite` is qualitative detection (presence). Their downstream interpretation differs.
- **Compartment matters.** Extracellular metabolites measure excretion / uptake / spent media; intracellular measure pool. Filter by compartment.
- **Targeted panel ≠ full metabolome.** Absence in measurement ≠ absence in cell.
- **Replicate / normalisation conventions vary by paper.** Read the paper before averaging.

### Discovery

```python
# Find metabolomics experiments
result = list_experiments(omics_types=["METABOLOMICS"], summary=False)

# Find papers
result = list_publications(omics_types=["METABOLOMICS"])
```

### Assay → metabolite drill-down (run_cypher)

```python
result = run_cypher(
    """
    MATCH (p:Publication {doi: $doi})<-[:Reported_in]-(e:Experiment)
          -[:Has_metabolite_assay]->(a:MetaboliteAssay)
          -[r:Assay_quantifies_metabolite]->(m:Metabolite)
    RETURN m.preferred_name AS metabolite,
           m.compartment AS compartment,
           r AS quantification,  // edge properties (varies by paper — see audit)
           e.background_factors AS condition
    ORDER BY metabolite
    LIMIT 50
    """,
    parameters={"doi": "10.../capovilla2023"},
)
```

### Metabolite → assay reverse lookup

```python
result = run_cypher(
    """
    MATCH (m:Metabolite {kegg_id: $kegg_id})
          <-[r:Assay_quantifies_metabolite|Assay_flags_metabolite]-(a:MetaboliteAssay)
          <-[:Has_metabolite_assay]-(e:Experiment)
    RETURN type(r) AS evidence_kind,
           e.experiment_id AS experiment,
           e.background_factors AS condition,
           m.compartment AS compartment
    """,
    parameters={"kegg_id": "C00041"},
)
# Note `evidence_kind` discriminates Quantifies (concentration) vs Flags (presence).
```

See `docs://examples/metabolites.py` scenario 8 for a runnable measurement query.
```

- [ ] **Step 2: Verify the analysis doc auto-registers as `docs://analysis/metabolites`.**

The auto-registration loop at `multiomics_explorer/mcp_server/server.py:71-86` picks up any `*.md` file under `references/analysis/`. To verify:

```bash
uv run multiomics-kg-mcp &
SERVER_PID=$!
sleep 2
# Check the resource is listed by introspecting the running server's resource registry
# (or via an MCP client if available)
kill $SERVER_PID
```

A simpler check: read `server.py` to confirm `_DOC_DIRS` still has the loop and the new file path matches:

```bash
grep -n "_DOC_DIRS\|references/analysis" multiomics_explorer/mcp_server/server.py
ls multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
```

Expected: file exists; loop present at lines 71-86; no code change needed.

The user will `/mcp` restart before testing the resource is available — note this in the commit message so they know.

- [ ] **Step 3: Commit Track B + register-verification.**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md
git commit -m "$(cat <<'EOF'
docs(analysis): metabolites Track B — measurement (run_cypher patterns)

Discovery via list_experiments(omics_types=['METABOLOMICS']);
assay→metabolite and metabolite→assay run_cypher patterns; full
caveat surfacing (no gene anchor, Quantifies vs Flags, compartment,
targeted panel, replicate/normalisation conventions vary).

Auto-registers as docs://analysis/metabolites via server.py:71-86
loop — no code change. User: /mcp restart before testing the resource.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase D — Example python (TDD per scenario)

### Task D1: Skeleton + CLI dispatcher + scenario stubs

**Files:**
- Create: `examples/metabolites.py`

- [ ] **Step 1: Write the file skeleton with all 8 scenario stubs.**

```python
"""Example: working with metabolites in the KG.

Demonstrates the three Metabolite-source pipelines (transport / gene reaction /
metabolomics) and the workflow patterns for each. See
docs://analysis/metabolites for the LLM-facing guide; this script is its
runnable companion.

Each scenario function names the source(s) it touches and the metabolite-source
caveat it surfaces. Print intermediate envelope state to teach the LLM how to
read responses, not just consume detail rows.

Run with: uv run python examples/metabolites.py --scenario <name>

Scenarios:
  1. discover         — element + pathway filter (sources: reaction + transport)
  2. compound_to_genes— evidence_source split (sources: reaction + transport)
  3. gene_to_metabolites — element signature + top_pathways (reaction + transport)
  4. cross_feeding    — bridge MED4 → ALT (reaction + transport)
  5. n_source_de      — N-source primitive → DE (reaction + transport → expression)
  6. tcdb_chain       — TCDB ontology → metabolite (transport)
  7. precision_tier   — family_inferred warning interpretation (transport)
  8. measurement      — metabolomics via run_cypher (measurement; native tools pending)
"""
from __future__ import annotations

import argparse
import sys
from typing import Callable

from multiomics_explorer import (
    differential_expression_by_gene,
    genes_by_metabolite,
    list_experiments,
    list_metabolites,
    metabolites_by_gene,
    run_cypher,
    search_ontology,
)


def scenario_discover() -> None:
    """Use this when the user asks 'what N-bearing metabolites does the KG track?'

    Sources: reaction + transport (both annotation arms surface chemistry).
    Caveat surfaced: none specific (this is a discovery primitive).
    """
    raise NotImplementedError


def scenario_compound_to_genes() -> None:
    """Use this when the user asks 'which MED4 genes act on glucose?'

    Sources: reaction + transport (response is split by evidence_source).
    Caveat surfaced: metabolism vs transport semantics differ; row counts
    are not comparable (transport rows often family_inferred).
    """
    raise NotImplementedError


def scenario_gene_to_metabolites() -> None:
    """Use this when the user asks 'what metabolites does PMM0001 act on?'

    Sources: reaction + transport.
    Caveat surfaced: chemistry-side `top_pathways` (Reaction-anchored) is
    NOT the same surface as gene-KO pathways from `genes_by_ontology(ontology='kegg')`.
    """
    raise NotImplementedError


def scenario_cross_feeding() -> None:
    """Use this when the user asks 'what could MED4 produce that ALT might consume?'

    Sources: reaction + transport (annotation-only).
    Caveat surfaced: KG is annotation-only — direction-of-cross-feeding
    not represented; conclusions are 'compatible with' not 'confirmed'.
    """
    raise NotImplementedError


def scenario_n_source_de() -> None:
    """Use this when the user asks 'which N-acting genes respond to N starvation?'

    Sources: reaction + transport → expression (chemistry filters DE input).
    Caveat surfaced: promiscuous enzymes / family_inferred transport can
    inflate the gene set fed to DE — tighten with evidence_sources or
    transport_confidence if results are noisy.
    """
    raise NotImplementedError


def scenario_tcdb_chain() -> None:
    """Use this when the user asks 'which MED4 genes transport glycine betaine?'

    Sources: transport (TCDB ontology bridge to metabolite-anchored route).
    Caveat surfaced: substrate-anchored route (`genes_by_metabolite`) is
    preferred over family-anchored route (`genes_by_ontology(ontology='tcdb')`)
    for cross-family substrate hits.
    """
    raise NotImplementedError


def scenario_precision_tier() -> None:
    """Use this when interpreting a `genes_by_metabolite` result with the
    family_inferred-dominance auto-warning.

    Sources: transport (warning is transport-arm specific).
    Caveat surfaced: ABC superfamily inflates family_inferred row counts;
    tighten via transport_confidence='substrate_confirmed' for high-confidence
    rows only.
    """
    raise NotImplementedError


def scenario_measurement() -> None:
    """Use this when the user asks 'what metabolites were measured under N starvation?'

    Sources: metabolomics measurement (no gene anchor).
    Caveat surfaced: native tools pending — uses `run_cypher`. Read the
    `Assay_quantifies` vs `Assay_flags` discriminator; compartment matters;
    targeted panel ≠ full metabolome.
    """
    raise NotImplementedError


SCENARIOS: dict[str, Callable[[], None]] = {
    "discover": scenario_discover,
    "compound_to_genes": scenario_compound_to_genes,
    "gene_to_metabolites": scenario_gene_to_metabolites,
    "cross_feeding": scenario_cross_feeding,
    "n_source_de": scenario_n_source_de,
    "tcdb_chain": scenario_tcdb_chain,
    "precision_tier": scenario_precision_tier,
    "measurement": scenario_measurement,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=sorted(SCENARIOS.keys()),
        help="Which scenario to run",
    )
    args = parser.parse_args()
    SCENARIOS[args.scenario]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify the file at least imports cleanly and `--help` works.**

Run:

```bash
uv run python examples/metabolites.py --help
```

Expected: argparse prints the choices `compound_to_genes`, `cross_feeding`, `discover`, `gene_to_metabolites`, `measurement`, `n_source_de`, `precision_tier`, `tcdb_chain`. No import errors.

If any import fails (e.g., a function not yet in `multiomics_explorer.__init__`), trim the import to only the names actually re-exported and add a TODO comment naming the missing import; subsequent task steps will surface this as a build-derived item for the audit's second pass.

- [ ] **Step 3: Commit the skeleton.**

```bash
git add examples/metabolites.py
git commit -m "$(cat <<'EOF'
feat(examples): metabolites.py skeleton + 8-scenario CLI

All scenarios stubbed (NotImplementedError). Argparse dispatch via
--scenario. Each docstring names: trigger ('Use this when ...'),
source(s) touched, caveat surfaced. Subsequent commits implement
each scenario via TDD.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D2: Add the smoke-test harness in test_examples.py

**Files:**
- Modify: `tests/integration/test_examples.py`

- [ ] **Step 1: Append the metabolites parametrised test.**

Append (do NOT replace existing content):

```python
# --- metabolites.py ---

METABOLITES_SCRIPT = REPO_ROOT / "examples" / "metabolites.py"

METABOLITES_SCENARIOS = [
    "discover",
    "compound_to_genes",
    "gene_to_metabolites",
    "cross_feeding",
    "n_source_de",
    "tcdb_chain",
    "precision_tier",
    "measurement",
]


@pytest.mark.parametrize("scenario", METABOLITES_SCENARIOS)
def test_metabolites_scenario_runs_cleanly(scenario):
    """Each metabolites.py scenario exits 0 and produces some output on the live KG."""
    cmd = [sys.executable, str(METABOLITES_SCRIPT), "--scenario", scenario]
    result = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=180
    )
    assert result.returncode == 0, (
        f"metabolites scenario {scenario} failed: stderr={result.stderr}"
    )
    assert result.stdout.strip(), (
        f"metabolites scenario {scenario} produced no output"
    )
```

- [ ] **Step 2: Run the new tests to verify they fail with `NotImplementedError`.**

```bash
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg
```

Expected: 8 failures, each with `NotImplementedError` in stderr, exit code != 0.

- [ ] **Step 3: Commit the test harness.**

```bash
git add tests/integration/test_examples.py
git commit -m "test(integration): metabolites.py smoke test (8 scenarios, all failing)

TDD checkpoint: all 8 scenarios fail with NotImplementedError as expected.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D3: Implement scenario `discover`

**Files:**
- Modify: `examples/metabolites.py` (replace `scenario_discover` body)

- [ ] **Step 1: Replace the `NotImplementedError` body with the scenario implementation.**

```python
def scenario_discover() -> None:
    """Use this when the user asks 'what N-bearing metabolites does the KG track?'

    Sources: reaction + transport (both annotation arms surface chemistry).
    Caveat surfaced: none specific (this is a discovery primitive).
    """
    print("=== Scenario: discover ===")
    print("Question class: 'what metabolites match these chemistry filters?'")
    print()

    result = list_metabolites(
        elements=["N"],
        organism_names=["MED4"],
        limit=5,
    )
    print(f"returned={result['returned']}  truncated={result['truncated']}")
    print(f"top_pathways: {[p['term_name'] for p in result.get('top_pathways', [])][:5]}")
    print(f"by_evidence_source: {result.get('by_evidence_source', {})}")
    print(f"top_organisms: {[o['preferred_name'] for o in result.get('top_organisms', [])][:5]}")
    print()
    print("First 5 metabolites:")
    for row in result["results"][:5]:
        print(f"  {row['metabolite_id']:<12} {row['preferred_name']:<40}  "
              f"gene_count={row.get('gene_count')}  transporter_count={row.get('transporter_count')}")
```

- [ ] **Step 2: Run the scenario and verify it passes the integration test.**

```bash
uv run python examples/metabolites.py --scenario discover
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg -k discover
```

Expected: scenario prints 5 rows; pytest reports 1 passed.

- [ ] **Step 3: Commit.**

```bash
git add examples/metabolites.py
git commit -m "feat(examples): metabolites.py scenario 1 — discover

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D4: Implement scenario `compound_to_genes`

**Files:**
- Modify: `examples/metabolites.py` (replace `scenario_compound_to_genes` body)

- [ ] **Step 1: Replace the body.**

```python
def scenario_compound_to_genes() -> None:
    """Use this when the user asks 'which MED4 genes act on glucose?'

    Sources: reaction + transport (response is split by evidence_source).
    Caveat surfaced: metabolism vs transport semantics differ; row counts
    are not comparable (transport rows often family_inferred).
    """
    print("=== Scenario: compound_to_genes ===")
    print("Question class: 'which genes catalyse / transport this compound?'")
    print()

    # Glucose: KEGG C00031
    result = genes_by_metabolite(
        metabolite_ids=["C00031"],
        organism="MED4",
        limit=10,
    )
    print(f"returned={result['returned']}  truncated={result['truncated']}")

    # Read the evidence_source split — KEY LESSON
    by_evidence = {}
    for row in result["results"]:
        by_evidence.setdefault(row["evidence_source"], 0)
        by_evidence[row["evidence_source"]] += 1
    print(f"by_evidence_source (in returned rows): {by_evidence}")
    print(f"warnings: {result.get('warnings', [])}")
    print()
    print("First 10 (gene, metabolite, evidence_source, transport_confidence):")
    for row in result["results"][:10]:
        ec = row.get("ec_number") or "-"
        tc = row.get("transport_confidence") or "-"
        print(f"  {row['locus_tag']:<10} {row['evidence_source']:<12} "
              f"transport_conf={tc:<22} ec={ec}")
```

- [ ] **Step 2: Run and verify.**

```bash
uv run python examples/metabolites.py --scenario compound_to_genes
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg -k compound_to_genes
```

Expected: PASS.

- [ ] **Step 3: Commit.**

```bash
git add examples/metabolites.py
git commit -m "feat(examples): metabolites.py scenario 2 — compound_to_genes (evidence_source split)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D5: Implement scenario `gene_to_metabolites`

**Files:**
- Modify: `examples/metabolites.py` (replace `scenario_gene_to_metabolites` body)

- [ ] **Step 1: Replace the body.**

```python
def scenario_gene_to_metabolites() -> None:
    """Use this when the user asks 'what metabolites does PMM0001 act on?'

    Sources: reaction + transport.
    Caveat surfaced: chemistry-side `top_pathways` (Reaction-anchored) is
    NOT the same surface as gene-KO pathways from `genes_by_ontology(ontology='kegg')`.
    """
    print("=== Scenario: gene_to_metabolites ===")
    print("Question class: 'what does this gene act on (chemistry)?'")
    print()

    result = metabolites_by_gene(
        locus_tags=["PMM0001"],
        organism="MED4",
        limit=10,
    )
    print(f"returned={result['returned']}  truncated={result['truncated']}")
    print(f"by_element (chemistry signature): {result.get('by_element', {})}")
    print()
    # KEY LESSON: chemistry top_pathways ≠ KEGG-KO pathways
    chem_pathways = result.get("top_pathways", [])
    print(f"top_pathways (chemistry-side, via Reaction → KeggPathway): "
          f"{[(p['term_id'], p['term_name']) for p in chem_pathways[:5]]}")
    print("NOTE: this is NOT the same surface as gene-KO pathways from")
    print("      genes_by_ontology(ontology='kegg', term_ids=...) — that's KO-anchored.")
    print()
    print("First 10 (metabolite, evidence_source, transport_confidence):")
    for row in result["results"][:10]:
        tc = row.get("transport_confidence") or "-"
        print(f"  {row['metabolite_id']:<12} {row['preferred_name']:<35} "
              f"{row['evidence_source']:<12} transport_conf={tc}")
```

- [ ] **Step 2: Run and verify.**

```bash
uv run python examples/metabolites.py --scenario gene_to_metabolites
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg -k gene_to_metabolites
```

Expected: PASS.

- [ ] **Step 3: Commit.**

```bash
git add examples/metabolites.py
git commit -m "feat(examples): metabolites.py scenario 3 — gene_to_metabolites (top_pathways distinction)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D6: Implement scenario `cross_feeding`

**Files:**
- Modify: `examples/metabolites.py` (replace `scenario_cross_feeding` body)

- [ ] **Step 1: Replace the body.**

```python
def scenario_cross_feeding() -> None:
    """Use this when the user asks 'what could MED4 produce that ALT might consume?'

    Sources: reaction + transport (annotation-only).
    Caveat surfaced: KG is annotation-only — direction-of-cross-feeding
    not represented; conclusions are 'compatible with' not 'confirmed'.
    """
    print("=== Scenario: cross_feeding (Workflow B') ===")
    print("Question class: 'between-organism metabolic coupling candidates'")
    print()

    # 1. Harvest MED4-side metabolites for a small gene set.
    med4_locus = ["PMM0001", "PMM0002", "PMM0003", "PMM0004", "PMM0005"]
    print(f"Step 1: MED4 chemistry for {med4_locus}")
    med4 = metabolites_by_gene(
        locus_tags=med4_locus,
        organism="MED4",
        summary=True,
    )
    metabolite_ids = [m["metabolite_id"] for m in med4.get("top_metabolites", [])][:10]
    print(f"  → harvested {len(metabolite_ids)} metabolite_ids: {metabolite_ids[:5]}...")
    print()

    if not metabolite_ids:
        print("(no metabolites — try larger MED4 gene set)")
        return

    # 2. Find ALT-side genes that touch any of those metabolites.
    print(f"Step 2: which ALT genes touch any of the {len(metabolite_ids)} metabolites?")
    alt = genes_by_metabolite(
        metabolite_ids=metabolite_ids,
        organism="ALT_MACL",
        limit=10,
    )
    print(f"  → returned={alt['returned']}  truncated={alt['truncated']}")
    print(f"  CAVEAT: KG is annotation-only — these are 'compatible with cross-feeding',")
    print(f"  not 'confirmed cross-feeding'. The Track-B measurement layer can corroborate.")
    print()
    print("First 10 ALT consumer candidates:")
    for row in alt["results"][:10]:
        print(f"  {row['locus_tag']:<10} → {row['metabolite_id']:<12} "
              f"({row['evidence_source']})")
```

- [ ] **Step 2: Run and verify.**

```bash
uv run python examples/metabolites.py --scenario cross_feeding
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg -k cross_feeding
```

Expected: PASS. (If ALT organism name differs in the live KG, adjust to the correct preferred_name — record any change as a build-derived audit item.)

- [ ] **Step 3: Commit.**

```bash
git add examples/metabolites.py
git commit -m "feat(examples): metabolites.py scenario 4 — cross_feeding (MED4 → ALT bridge)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D7: Implement scenario `n_source_de`

**Files:**
- Modify: `examples/metabolites.py` (replace `scenario_n_source_de` body)

- [ ] **Step 1: Replace the body.**

```python
def scenario_n_source_de() -> None:
    """Use this when the user asks 'which N-acting genes respond to N starvation?'

    Sources: reaction + transport → expression (chemistry filters DE input).
    Caveat surfaced: promiscuous enzymes / family_inferred transport can
    inflate the gene set fed to DE — tighten with evidence_sources or
    transport_confidence if results are noisy.
    """
    print("=== Scenario: n_source_de ===")
    print("Question class: 'which N-acting genes respond to N starvation?'")
    print()

    # 1. Get a candidate MED4 gene pool (small, illustrative).
    pool = ["PMM0001", "PMM0002", "PMM0003", "PMM0004", "PMM0005",
            "PMM1428", "PMM0532", "PMM0374", "PMM0533", "PMM0534"]

    # 2. Filter to N-bearing chemistry.
    print(f"Step 1: filter pool ({len(pool)} genes) to N-bearing chemistry")
    chem = metabolites_by_gene(
        locus_tags=pool,
        organism="MED4",
        metabolite_elements=["N"],
        summary=True,
    )
    n_genes = sorted({g["locus_tag"] for g in chem.get("top_genes", [])})
    print(f"  → {len(n_genes)} N-acting genes: {n_genes[:5]}...")
    print(f"  CAVEAT: pool may include promiscuous-enzyme / family_inferred-transport hits.")
    print(f"  To tighten: add evidence_sources=['metabolism'] or "
          f"transport_confidence='substrate_confirmed'.")
    print()

    if not n_genes:
        print("(no N-acting genes in pool — try a larger or differently-curated pool)")
        return

    # 3. DE on those genes.
    print(f"Step 2: DE for {len(n_genes)} N-acting genes")
    de = differential_expression_by_gene(
        organism="MED4",
        locus_tags=n_genes,
        direction="both",
        significant_only=True,
        limit=10,
    )
    print(f"  → returned={de['returned']}  truncated={de['truncated']}")
    print(f"  by_treatment_type: {de.get('by_treatment_type', {})}")
    print()
    print("First 10 (gene, treatment, log2FC, p_value):")
    for row in de["results"][:10]:
        print(f"  {row['locus_tag']:<10} {str(row.get('treatment_type', '-')):<25} "
              f"log2FC={row.get('log2_fold_change'):.3f}  p={row.get('p_value_adj'):.3g}")
```

- [ ] **Step 2: Run and verify.**

```bash
uv run python examples/metabolites.py --scenario n_source_de
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg -k n_source_de
```

Expected: PASS. (If no N-acting genes are found in the pool, adjust to a larger pool — log as build-derived audit item: "small fixed pool insufficient for chemistry-filtered DE; consider chemistry-filtered pool selection as a workflow primitive".)

- [ ] **Step 3: Commit.**

```bash
git add examples/metabolites.py
git commit -m "feat(examples): metabolites.py scenario 5 — n_source_de (chemistry-filtered DE)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D8: Implement scenario `tcdb_chain`

**Files:**
- Modify: `examples/metabolites.py` (replace `scenario_tcdb_chain` body)

- [ ] **Step 1: Replace the body.**

```python
def scenario_tcdb_chain() -> None:
    """Use this when the user asks 'which MED4 genes transport glycine betaine?'

    Sources: transport (TCDB ontology bridge to metabolite-anchored route).
    Caveat surfaced: substrate-anchored route (`genes_by_metabolite`) is
    preferred over family-anchored route (`genes_by_ontology(ontology='tcdb')`)
    for cross-family substrate hits.
    """
    print("=== Scenario: tcdb_chain ===")
    print("Question class: 'which genes transport this substrate?' "
          "(substrate-anchored, not family-anchored)")
    print()

    # 1. (Optional) confirm substrate is in the KG via search.
    print("Step 1: locate substrate via search_ontology (illustrative — not strictly needed)")
    found = search_ontology(query="glycine betaine", limit=5)
    print(f"  search returned {found['returned']} ontology terms (top tier rolls up to TCDB families).")
    print()

    # 2. Substrate-anchored route — direct.
    # Glycine betaine: KEGG C00719
    print("Step 2: substrate-anchored — genes_by_metabolite(['C00719'], evidence_sources=['transport'])")
    result = genes_by_metabolite(
        metabolite_ids=["C00719"],
        organism="MED4",
        evidence_sources=["transport"],
        limit=10,
    )
    print(f"  returned={result['returned']}  truncated={result['truncated']}")
    print(f"  warnings: {result.get('warnings', [])}")
    print()
    print("First 10 transporter candidates:")
    for row in result["results"][:10]:
        tc = row.get("transport_confidence") or "-"
        print(f"  {row['locus_tag']:<10} transport_conf={tc:<22} family={row.get('tcdb_family_id', '-')}")
    print()
    print("NOTE: prefer this substrate-anchored route over genes_by_ontology(ontology='tcdb').")
    print("      The latter is family-anchored — misses substrates curated by other families.")
```

- [ ] **Step 2: Run and verify.**

```bash
uv run python examples/metabolites.py --scenario tcdb_chain
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg -k tcdb_chain
```

Expected: PASS.

- [ ] **Step 3: Commit.**

```bash
git add examples/metabolites.py
git commit -m "feat(examples): metabolites.py scenario 6 — tcdb_chain (substrate-anchored route)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D9: Implement scenario `precision_tier`

**Files:**
- Modify: `examples/metabolites.py` (replace `scenario_precision_tier` body)

- [ ] **Step 1: Replace the body.**

```python
def scenario_precision_tier() -> None:
    """Use this when interpreting a `genes_by_metabolite` result with the
    family_inferred-dominance auto-warning.

    Sources: transport (warning is transport-arm specific).
    Caveat surfaced: ABC superfamily inflates family_inferred row counts;
    tighten via transport_confidence='substrate_confirmed' for high-confidence
    rows only.
    """
    print("=== Scenario: precision_tier ===")
    print("Question class: 'how do I interpret family_inferred-dominance warning?'")
    print()

    # 1. Trigger the warning by querying a broad substrate that ABC superfamily handles.
    print("Step 1: query broad substrate (no precision filter — likely fires warning)")
    broad = genes_by_metabolite(
        metabolite_ids=["C00041"],  # alanine — common ABC substrate
        organism="MED4",
        evidence_sources=["transport"],
        limit=5,
    )
    print(f"  warnings: {broad.get('warnings', [])}")
    print(f"  returned={broad['returned']}  truncated={broad['truncated']}")
    print(f"  total_rows={broad.get('total_rows', '-')}")
    print()

    # 2. Tighten to substrate_confirmed only.
    print("Step 2: tighten to transport_confidence='substrate_confirmed'")
    tight = genes_by_metabolite(
        metabolite_ids=["C00041"],
        organism="MED4",
        evidence_sources=["transport"],
        transport_confidence="substrate_confirmed",
        limit=5,
    )
    print(f"  warnings: {tight.get('warnings', [])}")
    print(f"  returned={tight['returned']}  truncated={tight['truncated']}")
    print()
    print("LESSON: when the warning fires, decide between:")
    print("  (a) keep all rows but explicitly call out family_inferred-vs-substrate_confirmed,")
    print("  (b) tighten to substrate_confirmed only (high precision, lower recall),")
    print("  (c) exclude promiscuous families via tcdb_family_ids (rarely needed).")
```

- [ ] **Step 2: Run and verify.**

```bash
uv run python examples/metabolites.py --scenario precision_tier
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg -k precision_tier
```

Expected: PASS. (If alanine doesn't trigger the warning in the live KG, swap to a substrate that does — record the swap as a build-derived audit observation: "auto-warning trigger conditions need clearer documentation".)

- [ ] **Step 3: Commit.**

```bash
git add examples/metabolites.py
git commit -m "feat(examples): metabolites.py scenario 7 — precision_tier (family_inferred warning)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D10: Implement scenario `measurement` (run_cypher)

**Files:**
- Modify: `examples/metabolites.py` (replace `scenario_measurement` body)

- [ ] **Step 1: Replace the body.**

```python
def scenario_measurement() -> None:
    """Use this when the user asks 'what metabolites were measured under N starvation?'

    Sources: metabolomics measurement (no gene anchor).
    Caveat surfaced: native tools pending — uses `run_cypher`. Read the
    `Assay_quantifies` vs `Assay_flags` discriminator; compartment matters;
    targeted panel ≠ full metabolome.
    """
    print("=== Scenario: measurement ===")
    print("Question class: 'what metabolites were measured under condition X?'")
    print()
    print(">>> BANNER: native tools pending — using run_cypher.")
    print(">>> See docs://analysis/metabolites Track B and the audit doc for the planned surface.")
    print()

    # 1. Find metabolomics experiments.
    print("Step 1: list_experiments(omics_types=['METABOLOMICS'])")
    exps = list_experiments(omics_types=["METABOLOMICS"], summary=False, limit=5)
    print(f"  returned={exps['returned']}  truncated={exps['truncated']}")
    for e in exps["results"][:5]:
        print(f"  {e['experiment_id']:<12} treatment={e.get('treatment_type')} "
              f"bg={e.get('background_factors')}")
    print()

    # 2. Walk one experiment → assays → metabolites via run_cypher.
    print("Step 2: assay → metabolite walk via run_cypher")
    cy = run_cypher(
        """
        MATCH (e:Experiment)-[]->(a:MetaboliteAssay)-[r:Assay_quantifies_metabolite|Assay_flags_metabolite]->(m:Metabolite)
        WHERE 'METABOLOMICS' IN coalesce(e.omics_type, [])
        RETURN type(r) AS evidence_kind,
               m.preferred_name AS metabolite,
               coalesce(m.compartment, '<missing>') AS compartment,
               e.experiment_id AS experiment,
               coalesce(e.background_factors, []) AS bg_factors
        ORDER BY metabolite, experiment
        LIMIT 20
        """,
    )
    print(f"  returned={cy['returned']}  truncated={cy['truncated']}")
    print(f"  warnings: {cy.get('warnings', [])}")
    print()
    print("First 20 measurement rows (evidence_kind | metabolite | compartment | experiment):")
    for row in cy["results"][:20]:
        print(f"  {row['evidence_kind']:<28} {row['metabolite']:<30} "
              f"{row['compartment']:<15} {row['experiment']}")
    print()
    print("CAVEATS to surface alongside any answer:")
    print("  - No gene anchor: cannot attribute these to specific genes.")
    print("  - Quantifies (concentration/intensity) vs Flags (qualitative detection).")
    print("  - Compartment matters — extracellular ≠ intracellular biology.")
    print("  - Targeted panel — absence in measurement ≠ absence in cell.")
```

- [ ] **Step 2: Run and verify.**

```bash
uv run python examples/metabolites.py --scenario measurement
uv run pytest tests/integration/test_examples.py::test_metabolites_scenario_runs_cleanly -v -m kg -k measurement
```

Expected: PASS.

If the Cypher fails because edge labels differ from `Has_metabolite_assay` / `Assay_quantifies_metabolite` / `Assay_flags_metabolite`: read `kg_schema` (or run a label-introspection query as in Task A1 Step 3), update the Cypher, and log the difference as a build-derived audit item ("Documentation: edge labels for metabolomics paths not surfaced in `kg_schema` at the level needed for run_cypher patterns").

- [ ] **Step 3: Commit.**

```bash
git add examples/metabolites.py
git commit -m "feat(examples): metabolites.py scenario 8 — measurement (run_cypher, native tools pending)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D11: Run the full suite + register the script

**Files:**
- Modify: `multiomics_explorer/mcp_server/server.py` (add static resource registration)
- Modify: `examples/README.md`

- [ ] **Step 1: Run all 8 scenarios + the smoke test.**

```bash
uv run pytest tests/integration/test_examples.py -v -m kg
```

Expected: 8 metabolites scenarios PASS (plus the existing pathway_enrichment scenarios per their current status).

- [ ] **Step 2: Register `metabolites.py` as a static MCP resource.**

In `multiomics_explorer/mcp_server/server.py`, after the existing `pathway_enrichment.py` registration (currently lines 91-99), add a parallel registration for `metabolites.py`. Replace the existing block:

```python
mcp.add_resource(
    FunctionResource.from_function(
        fn=(lambda p: lambda: p.read_text())(_EXAMPLES_DIR / "pathway_enrichment.py"),
        uri="docs://examples/pathway_enrichment.py",
        name="pathway_enrichment.py",
        description="Runnable example script for pathway enrichment",
        mime_type="text/x-python",
    )
)
```

with:

```python
for example_name, description in [
    ("pathway_enrichment.py", "Runnable example script for pathway enrichment"),
    ("metabolites.py", "Runnable example script for metabolites workflows (3 source pipelines, 8 scenarios)"),
]:
    mcp.add_resource(
        FunctionResource.from_function(
            fn=(lambda p: lambda: p.read_text())(_EXAMPLES_DIR / example_name),
            uri=f"docs://examples/{example_name}",
            name=example_name,
            description=description,
            mime_type="text/x-python",
        )
    )
```

This loop pattern keeps things DRY for future example additions.

- [ ] **Step 3: Update `examples/README.md`.**

Read the current file, then append (don't replace pathway_enrichment section):

```markdown

## `metabolites.py`

Eight scenarios across the three Metabolite-source pipelines (transport / gene reaction / metabolomics). See `docs://analysis/metabolites` for the LLM-facing workflow guide.

```bash
uv run python examples/metabolites.py --scenario discover
uv run python examples/metabolites.py --scenario compound_to_genes
uv run python examples/metabolites.py --scenario gene_to_metabolites
uv run python examples/metabolites.py --scenario cross_feeding
uv run python examples/metabolites.py --scenario n_source_de
uv run python examples/metabolites.py --scenario tcdb_chain
uv run python examples/metabolites.py --scenario precision_tier
uv run python examples/metabolites.py --scenario measurement
```

Exercised by `tests/integration/test_examples.py` under `-m kg`.
```

- [ ] **Step 4: Verify the server still imports cleanly.**

```bash
uv run python -c "from multiomics_explorer.mcp_server.server import mcp; print('ok')"
```

Expected: prints `ok`. If imports fail, fix and re-run.

- [ ] **Step 5: Commit Phase D.**

```bash
git add examples/metabolites.py examples/README.md multiomics_explorer/mcp_server/server.py
git commit -m "$(cat <<'EOF'
feat(examples): register metabolites.py as docs://examples/metabolites.py

- Refactored example registration to a loop (DRY for future additions).
- All 8 scenarios pass under `-m kg`.
- README updated with usage.

User: /mcp restart before testing the resource is available.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase E — Audit second pass (build-derived items)

### Task E1: Append build-derived rows to Part 2

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 2)

- [ ] **Step 1: Review notes accumulated during Phases C and D.**

While writing the analysis doc and example python, several build-derived observations should have been noted (in commit messages, scratchpad, or memory). Examples to look for:
- Did any tool need a chemistry rollup that didn't exist? → Part 2 build-derived row.
- Did any scenario require an awkward chain of calls that a single tool could have handled? → Part 3b build-derived new-tool proposal.
- Did any Cypher query require an edge label or property that should be surfaced via `kg_schema`? → Part 2 build-derived row on `kg_schema`.
- Did any scenario need a chemistry filter on an existing tool that didn't exist? → Part 2 build-derived row.

- [ ] **Step 2: Append build-derived rows to Part 2 table.**

Each new row: Tool, Current chemistry surfacing, Recommended change, Priority, Phase=`build-derived`, plus a "Surfaced by:" note in the recommended-change cell naming the analysis doc section or example scenario.

If no Part 2 build-derived items emerged, write a one-line note in the audit: "No build-derived Part 2 items in this pass." This is a valid outcome.

- [ ] **Step 3: Commit Part 2 second pass.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "audit(metabolites): Part 2 second pass — build-derived chemistry-annotation gaps

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task E2: Append build-derived rows to Part 3a

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 3a)

- [ ] **Step 1: Review.** Same approach as E1 but scoped to measurement-side mods.

- [ ] **Step 2: Append rows.** Same column shape; Phase=`build-derived`.

- [ ] **Step 3: Commit.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "audit(metabolites): Part 3a second pass — build-derived measurement-side mods

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task E3: Append build-derived new-tool proposals to Part 3b

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 3b)

- [ ] **Step 1: Review build phases for unmet workflow needs.**

Look for cases where the example python had to:
- Use `run_cypher` for a recurring pattern (suggests a missing tool).
- Chain three or more existing tools where the user need is a single workflow primitive.
- Implement awkward client-side filtering that should be a tool parameter.

Each becomes a build-derived new-tool proposal.

- [ ] **Step 2: Append proposals.**

Each: paragraph + signature sketch + `{recommendation, phase=build-derived, surfaced by}`. Recommendation tier per the same taxonomy. Surfaced-by names the analysis doc section or scenario.

- [ ] **Step 3: Refine first-pass proposals.**

Re-read each first-pass Part 3b proposal. For each, decide:
- **Validated** by the build (proposal stands; recommendation may strengthen).
- **Downgraded** (recommendation moves toward Nice-to-have or Not-needed).
- **Reshaped** (signature/scope changed — write the new shape in a "Refinement:" sub-bullet under the original entry).
- **Dropped** (rare; if the proposal is misconceived, remove and add a Part 4 question instead — see spec §5 edge case).

Mark each first-pass proposal with one of these annotations.

- [ ] **Step 4: Commit Part 3b second pass.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "audit(metabolites): Part 3b second pass — refinements + build-derived proposals

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task E4: Append build-derived KG-side asks (and finalise KG-MET-007 indexes)

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md` (Part 5)

- [ ] **Step 1: Identify build-derived KG asks.**

From Phases C and D, identify any of:
- Edge label / property needed for a Cypher query but absent (→ Data gap).
- Slow query (→ Index).
- Repeated traversal that should be a node-level rollup (→ Rollup).
- KG schema documentation gap that affected example python correctness (→ Documentation).

- [ ] **Step 2: Finalise KG-MET-007 (indexes).**

Replace the deferred KG-MET-007 entry with concrete index asks based on the actual queries used in scenarios 4, 5, 6, 7, 8, plus any audit Part 1 query that was slow. Each index ask names the query/scenario it accelerates.

- [ ] **Step 3: Append new build-derived asks.**

ID format: `KG-MET-009`, `KG-MET-010`, ... Each carries `{category, priority, phase=build-derived, ask, why}`.

- [ ] **Step 4: Update audit doc status.**

Change the doc's "Status:" header from "First pass in progress" to "Two-pass complete; ready for KG-side review and metabolomics-DM definition conversation."

- [ ] **Step 5: Commit Part 5 second pass + status flip.**

```bash
git add docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md
git commit -m "$(cat <<'EOF'
audit(metabolites): Part 5 second pass — build-derived KG asks; finalise

KG-MET-007 indexes filled in based on actual scenario queries.
KG-MET-009..N: build-derived asks surfaced during analysis-doc and
example-python builds. Audit status flipped to two-pass complete.

Ready for KG-side review and the metabolomics-DM definition
conversation. Plan execution complete.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase F — Walk-through with the user

### Task F1: Prepare and deliver walk-through

**Files:** none (this is a presentation step).

- [ ] **Step 1: Prepare a concise walk-through of the 8 example scenarios.**

For each scenario, prepare:
- The trigger condition (one sentence — when an LLM should reach for it).
- The Cypher / API call shape (one line summary).
- The caveat the scenario teaches.

- [ ] **Step 2: Prepare a concise walk-through of audit findings.**

For each part:
- Part 1: top 3 KG-inventory facts that matter most.
- Part 2: top P0/P1 chemistry-annotation gaps.
- Part 3a: top P0/P1 measurement-side existing-tool gaps.
- Part 3b: number of Must-add / Should-add / Pending-definition new-tool proposals; named highlights.
- Part 4: open definition questions, organised by source.
- Part 5: top P0/P1 KG asks; named highlights.

- [ ] **Step 3: Deliver the walk-through.**

Surface the summary to the user in chat, allowing them to drill into any scenario or audit row. The user explicitly requested this walk-through — the implementation is complete only after they have walked through it.

(No commit for this step — it's a conversational deliverable.)

---

## Risks & rollback

- **KG inventory queries time out.** Mitigation: every Cypher query in Phase A includes a `LIMIT` or aggregation; if a path traversal exceeds 30s, switch to property-existence-only counts and log the path as a build-derived `KG-MET-*` index ask in Phase E.
- **Edge labels in queries differ from the live KG.** Mitigation: Task A1 Step 3 introspects edge labels first; subsequent steps use the introspected values. If any later Cypher fails, treat as a documentation gap (add `KG-MET-*` Documentation ask).
- **A scenario can't be implemented because the existing API doesn't support it.** Mitigation: this is a build-derived signal — fall back to `run_cypher` in the scenario, log the gap as a Part 3b build-derived new-tool proposal, and tag the scenario's docstring with "currently uses run_cypher; see audit Part 3b."
- **MCP resource registration regression.** Mitigation: Task D11 Step 4 imports the server module to catch syntax / import errors before commit. If `/mcp` restart still fails for the user, revert the server.py change and re-run with the un-refactored single-resource pattern.
- **Plan execution interleaves with user changes on `main`.** Mitigation: each task commits independently. Rollback granularity is per-commit; nothing in this plan changes shared infrastructure or generated artifacts (no YAML edits, no `build_about_content.py` regen).

---

## Self-review checklist (run before invoking executing-plans / subagent-driven)

- [ ] Spec coverage: every spec §3.1 part has at least one task.
- [ ] Spec §3.2 (analysis doc): Task C1 (skeleton+disambig), C2 (A1), C3 (A2), C4 (A combined), C5 (B+register).
- [ ] Spec §3.3 (example python): Task D1 (skeleton), D2 (test harness), D3-D10 (one task per scenario), D11 (register+README+verify).
- [ ] Spec §5 order of work: Phase A (Part 1), Phase B (first pass Parts 2-5), Phase C+D (analysis doc + example), Phase E (second pass), Phase F (walk-through).
- [ ] Every task has explicit file paths.
- [ ] Every Python step has runnable code blocks.
- [ ] Every test step has the exact pytest command + expected outcome.
- [ ] Every commit step has a complete commit message via heredoc.
- [ ] No "TBD", "TODO", or "fill in" placeholders.
- [ ] Type/name consistency: scenario function names match keys in `SCENARIOS` dict; `--scenario` CLI choices match dict keys; integration test scenario list matches.
- [ ] Phase axis (`first-pass` / `build-derived`) applied consistently across audit Parts 2/3a/3b/5.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-04-metabolites-assets.md`.** Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
