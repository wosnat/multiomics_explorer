# MCP outfacing-docs readability pass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sweep all 37 MCP tools so their three outfacing surfaces (tool docstring + Pydantic field descriptions + per-tool YAML) read as a clean, self-consistent toolset rather than an archaeology layer of past specs, audits, and KG releases. Audience is an LLM agent calling MCP tools; optimize for correctness signal density.

**Architecture:** Edit-only documentation pass — no behavior change. Edits land in `multiomics_explorer/mcp_server/tools.py` (docstrings + Pydantic `Field(description=...)`) and `multiomics_explorer/inputs/tools/*.yaml`. Then `scripts/build_about_content.py` regenerates `multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md` (the served `docs://tools/{name}` resource). Four guide files at `docs://guide/*` are the shared preamble — per-tool docs cross-link to them rather than re-explain cross-cutting semantics.

**Tech Stack:** Python (FastMCP, Pydantic v2), YAML, custom build script (`scripts/build_about_content.py`).

**Spec:** [`docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md`](../specs/2026-05-07-mcp-docs-readability-pass-design.md)

---

## Style rules (the 9 rules — applied at every step)

Recap from spec. Read the spec for the full rationale; this is the working summary.

1. **No time-stamped counts** — drop "149 today", "3,025 today". Keep structurally bounded counts.
2. **No internal-history shorthand** — drop `§`, `Phase N`, `audit §`, `F1`, `D2`, `KG-MET-002`, `Mode-B`, `Cluster A`, `parent §10`.
3. **No release-date hedges** — drop "Phase 2 rename", "(KG release 2026-05-06)". **Carveout:** `[AQ]` and `[ENR]` drift markers stay as 1-line inline notes on affected tools.
4. **Cross-link only by stable URI** — `docs://...`, peer tool names. No commit SHAs, plan filenames, "spec §X".
5. **De-duplicate** — one canonical home per fact. Drop YAML `mistakes:` entries that restate Pydantic field descriptions.
6. **Pydantic field descriptions stay terse** — lead = type/semantics; second clause ≤ 1 example; no narrative.
7. **Docstrings stay tight** — 1 paragraph + 1 routing sentence. Defer dense prose to per-tool md.
8. **CLAUDE.md tool table out of scope.**
9. **Defer to guides for cross-cutting semantics — with two inline carveouts:**
   - Pydantic field descriptions always restate inline (the agent reads field-by-field).
   - 1-line YAML gotchas stay inline (cheaper than a cross-link fetch).

---

## File structure

| File | Modified per task | Purpose |
|---|---|---|
| `multiomics_explorer/mcp_server/tools.py` | every batch | Tool docstrings + `Field(description=...)` strings (params + per-result models) |
| `multiomics_explorer/inputs/tools/{tool}.yaml` | every batch | Per-tool `examples`, `mistakes`, `chaining`, `verbose_fields`, optional `response_notes` |
| `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{tool}.md` | every batch (regenerated) | Output of `scripts/build_about_content.py`; **never edited directly** |
| `scripts/build_about_content.py` | not modified | Renderer; out of scope per spec |
| `multiomics_explorer/skills/multiomics-kg-guide/references/guide/*.md` | only if Task 6 finds a contradiction | Cross-cutting guides; touch only if a per-tool edit reveals a guide is wrong |

---

## Verification commands (used throughout)

**Regenerate (after every per-tool batch):**

```bash
uv run python scripts/build_about_content.py
```

Default behavior: rebuilds every tool that has an input YAML. Writes directly to `multiomics_explorer/skills/multiomics-kg-guide/references/tools/`. No separate sync step.

**Lint regex (used on the regenerated md tree to check for style violations):**

```bash
grep -nE '\d{4}-\d{2}-\d{2}| today\b|Phase [0-9]|§|\baudit\b|KG-[A-Z]+-[0-9]|F[0-9] |D[0-9] |Mode-[A-Z]|Cluster [A-Z]|parent §' \
  multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md \
  | grep -v -E '\[AQ\]|\[ENR\]|annotation_quality|informative_only'
```

After the pass this should print nothing (or only justified hits — `[AQ]`/`[ENR]` carveouts are pre-filtered out by the second pipe). 138 violations exist today — final state should be 0 (modulo the carveouts).

**Smoke test (after every batch, before commit):**

```bash
pytest tests/unit/ -q
```

Expected: all green. Pydantic schema compilation + tool registry round-trip caught here.

---

## Task 0: Establish the editing template via a worked `list_metabolites` pass

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` (the `list_metabolites` function + `MetaboliteResult` + `ListMetabolitesResponse` + `MetMeasurementCoverage` Pydantic models)
- Modify: `multiomics_explorer/inputs/tools/list_metabolites.yaml`
- Verify: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolites.md` (regenerated)

This task does ONE tool end-to-end. The result becomes the reference template the later batch tasks copy from. Don't shortcut — show all 9 rules in action on this one file.

- [ ] **Step 1: Read the current state**

```bash
sed -n '1,5p' multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolites.md
```

Open these three files in parallel:
- `multiomics_explorer/mcp_server/tools.py` — search for `def list_metabolites`. Note the docstring + every `Field(description=...)` for parameters and inside `MetaboliteResult`, `ListMetabolitesResponse`, `MetMeasurementCoverage`.
- `multiomics_explorer/inputs/tools/list_metabolites.yaml` — note the `mistakes:` and `examples:` blocks.
- `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolites.md` — the current rendered output (do NOT edit, this is generated).

- [ ] **Step 2: Audit the current `list_metabolites.md` against the 9 rules**

Concrete violations expected (matched against rendered md today):

| Rule | Hit |
|---|---|
| 1 (stamped counts) | "Total Metabolite nodes in KG (unfiltered, 3,025 today)", "149 metabolites today", "22 metabolites are gene_count=0 today", "(149 today)", "Non-zero on 149 of 3230 metabolites today (~5% coverage; KG release 2026-05-06)" |
| 1 (stamped counts) | "1,563 today" (in `elements` description), "395 distinct pathways", "(450 of 3025 today)", "(1,097 today)", "(101 today)" |
| 3 (release dates) | "Phase 1 plumbing — spec §6.6", "(KG release 2026-05-06)", "post-TCDB", "renamed from `search` in Phase 2" |
| 2 (history shorthand) | "KG-MET-002", "Phase 1", "Phase 2" |
| 4 (cross-link via URI) | "spec §6.6" → drop |
| 5 (dedupe) | "Direction-agnostic" appears in docstring + `mistakes[0]` (paragraph form) — keep one short bullet in mistakes, defer full prose to `docs://guide/conventions`. "exclude wins on overlap" appears in `exclude_metabolite_ids` field + 2 mistakes entries — keep field description, drop mistakes restatement. "Hill-notation footgun" appears 3 times — keep one (in the `elements` field description). |
| 7 (tight docstring) | Current docstring is 4 paragraphs. Trim to 1 paragraph (what it does + 1-line routing). |
| 9 (defer to guides) | The "Direction-agnostic" multi-paragraph in docstring → 1 line + cross-link to `docs://guide/conventions`. The "presence-only" repetition → keep in `elements` field; drop from mistakes. |

- [ ] **Step 3: Edit the `list_metabolites` tool docstring in `mcp_server/tools.py`**

Find the `list_metabolites` async wrapper. Its docstring is the agent-facing description. Replace with:

```
Browse and filter metabolites in the chemistry layer (KEGG-curated metabolism + TCDB-curated transport substrates + measured by MetaboliteAssay).

Routing: drill into `genes_by_metabolite(metabolite_ids=[...])` for catalysts/transporters per organism, `assays_by_metabolite(metabolite_ids=[...])` for measurement evidence, `genes_by_ontology(ontology='kegg', term_ids=[pathway_id])` for pathway → genes. See `docs://guide/conventions` for direction-agnosticism, `docs://analysis/metabolites` for the 3 source pipelines decision tree.
```

Anything else currently in the docstring (multi-paragraph "Direction-agnostic. Joins through... layer transcriptional evidence...", "presence-only", "After this tool drill in via:") — delete. The cross-link covers it.

- [ ] **Step 4: Edit the Pydantic field descriptions in `mcp_server/tools.py`**

For the `list_metabolites` parameters and the `MetaboliteResult` / `ListMetabolitesResponse` / `MetMeasurementCoverage` models, apply rules 1, 3, 6 to every `Field(description=...)`:

- Drop "(149 today)", "(~22% of metabolites)", "(3,025 today)", "(101 today)", etc. — replace with "small subset", "common", "rare", or just delete the parenthetical.
- Drop "(KG release 2026-05-06)", "Phase 1 plumbing — spec §6.6".
- Lead with type/semantics; second clause ≤ 1 example. E.g. `pathway_ids` description trims to: `"Filter by KEGG pathway membership (KeggTerm.id). E.g. ['kegg.pathway:ko00910']. Joined via Metabolite_in_pathway. not_found.pathway_ids lists unknown IDs."`
- For `evidence_sources`, keep the Literal-bounded list `(metabolism / transport / metabolomics)` — that's structurally bounded, rule 1 doesn't apply.
- For `gene_count` (per-result field): drop "22 metabolites are gene_count=0 today; check evidence_sources to confirm — 0 ≠ 'absent from KG'." Replace with: "0 on metabolomics-only metabolites (measured by MetaboliteAssay but not reachable via any gene catalysis or transport path); check evidence_sources."
- For `transporter_count`: drop "e.g. 17 for glucose, 229 for sodium". Drop "(2026-05-03 rollup)". Keep "Scoped to leaves (`tc_specificity`)." that's the substantive part.
- For `measured_paper_count`: drop "Non-zero on 149 metabolites today: 5 measured by all 3 papers, 25 by 2, 119 by 1." Replace with: "Distinct papers measuring this metabolite. Non-zero on metabolites with metabolomics evidence."
- For `measured_compartments`: drop "Populated by post-import on all 149 measured metabolites; [] on the 3081 unmeasured." Replace with: "Wet-lab compartments observed (subset of {'whole_cell', 'extracellular', 'vesicle'}). Empty on unmeasured metabolites — use len(measured_compartments) >= 1 to filter."

Per the rule-9 carveout, every Pydantic field description **stays inline** with a 1-clause restatement of the relevant semantics. Do not replace a field description with "see docs://guide/conventions" — the agent reads the params table field-by-field.

- [ ] **Step 5: Edit `multiomics_explorer/inputs/tools/list_metabolites.yaml`**

`mistakes:` block — current state is 11 entries. Apply rules 5 and 9:

Drop entries that restate a Pydantic field description (rule 5):
- Entry 2 ("elements is presence-only, AND-of...") — `elements` field description already says this. **Drop.**
- Entry 9 ("Per-row `elements` is a presence list — no atom counts") — duplicate of entry 2 with different framing. **Drop.**
- Entry 10 (currency-cofactor strip) — partially restates `exclude_metabolite_ids` field description. **Drop the "Set-difference semantics with `metabolite_ids`" sentence.** Keep the cofactor list (that's the agent-useful gotcha).
- Last entry (cross-link to `docs://analysis/metabolites`) — keep, this is rule 4 well-applied.

Drop entries that have multi-paragraph length and are pure cross-cutting (rule 9):
- Entry 1 ("Direction-agnostic. Joining through..." — 3 sentences) → replace with a 1-line: `"Direction-agnostic — KEGG equation order is unreliable upstream. See docs://guide/conventions."`

Drop time-stamped counts (rule 1):
- Entry 3 ("22 such metabolites today") → reword: `"gene_count=0 indicates a metabolomics-only metabolite (measured by mass spec but not reachable via any gene catalysis or transport path). Check evidence_sources to confirm — 0 ≠ 'absent from KG'."`
- Entry 6 ("149 today") → reword: `"evidence_sources='metabolomics' selects metabolites measured by a MetaboliteAssay. Drill in via list_metabolite_assays(metabolite_ids=[...]) or assays_by_metabolite."`
- Entry 7 ("populated on all 107 measured metabolites...defaults to `[]` on the 3111 unmeasured...KG-MET-002") → reword to drop the count and the KG-id: `"Same metabolite measured in both whole_cell and extracellular returns one row with measured_compartments=['extracellular','whole_cell'] (sorted), not two rows. Metabolite is compartment-agnostic."`

Final `mistakes:` should be roughly 7 entries (down from 11).

`examples:` block — drop "# Phase 1 plumbing — spec §6.6" inline comment from the Example 6 response. Otherwise leave examples intact.

- [ ] **Step 6: Regenerate**

```bash
uv run python scripts/build_about_content.py list_metabolites
```

Expected output:
```
  OK   list_metabolites: multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolites.md [built]
```

- [ ] **Step 7: Verify the regenerated md against the 9 rules**

```bash
grep -nE '\d{4}-\d{2}-\d{2}| today\b|Phase [0-9]|§|\baudit\b|KG-[A-Z]+-[0-9]|F[0-9] |D[0-9] |Mode-[A-Z]|Cluster [A-Z]|parent §' \
  multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolites.md \
  | grep -v -E '\[AQ\]|\[ENR\]|annotation_quality|informative_only'
```

Expected: empty output. If any line surfaces, fix the source (tools.py or YAML) and re-run Step 6.

Eyeball the rendered md:
- "What it does" section should be ≤ 6 lines.
- Params table descriptions should be tight (no time-stamps, no `§`).
- "Common mistakes" / "Good to know" should be ≤ 7 entries with no duplicate semantics.

- [ ] **Step 8: Smoke test**

```bash
pytest tests/unit/ -q
```

Expected: all green. (No code changed — only docstrings and field descriptions. But Pydantic field-description edits are evaluated at module import time, so a typo would surface here.)

- [ ] **Step 9: Commit Task 0 separately**

```bash
git add multiomics_explorer/mcp_server/tools.py \
        multiomics_explorer/inputs/tools/list_metabolites.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolites.md
git commit -m "$(cat <<'EOF'
docs(mcp): readability pass — list_metabolites (template)

Worked example for the readability pass: applies the 9 style rules to
list_metabolites end-to-end. Subsequent batches follow the same
pattern. Spec: docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Batch 1 — discovery + identity (9 tools)

**Files (edit per tool, regenerate, commit once at end):**
- Modify: `multiomics_explorer/mcp_server/tools.py` (functions + Pydantic models for the 9 tools)
- Modify: `multiomics_explorer/inputs/tools/{kg_schema,resolve_gene,gene_overview,gene_details,genes_by_function,list_organisms,list_publications,list_experiments,list_filter_values}.yaml`
- Regenerated: corresponding 9 md files in `multiomics_explorer/skills/multiomics-kg-guide/references/tools/`

Tools: `kg_schema`, `resolve_gene`, `gene_overview`, `gene_details`, `genes_by_function`, `list_organisms`, `list_publications`, `list_experiments`, `list_filter_values`.

For each tool, follow Task 0's per-tool pattern:
1. Audit against the 9 rules.
2. Edit docstring (rule 7) + Pydantic field descriptions (rules 1, 3, 6) in `tools.py`.
3. Edit YAML (rules 5, 9) in `inputs/tools/{tool}.yaml`.
4. Regenerate that one tool: `uv run python scripts/build_about_content.py {tool}`.
5. Lint-check the regenerated md.

Tool-specific notes from a pre-audit:

| Tool | Likely violations |
|---|---|
| `gene_overview` | `[AQ]` carveout per rule 3 — keep "annotation_quality redefined May 2026 KG release" inline as 1 line. Cross-link rest to `docs://guide/conventions`. Drop time-stamped counts. |
| `gene_details` | Same `[AQ]` carveout. |
| `genes_by_function` | Same `[AQ]` carveout. The docstring currently restates Lucene syntax — rule 9 cross-link to `docs://guide/conventions` (Lucene score fields section). |
| `list_experiments` | Likely "table_scope" notes — keep tool-specific spin (rule 9 carveout — table_scope tested-absent interaction is tool-specific). Drop time-stamps. |
| `list_organisms` | Likely "by_measurement_capability" notes with stamped counts. Drop counts; keep the rollup description. |
| `list_publications` | Similar to `list_organisms`. |
| `list_filter_values` | Probably already terse (small surface). Quick pass. |
| `kg_schema` | Probably already terse (introspection tool). Quick pass. |
| `resolve_gene` | Probably already terse. Quick pass. |

- [ ] **Step 1: Edit `kg_schema`** — audit + apply 9 rules + regenerate that tool only.
- [ ] **Step 2: Edit `resolve_gene`** — audit + apply 9 rules + regenerate that tool only.
- [ ] **Step 3: Edit `gene_overview`** — audit + apply 9 rules + regenerate. **AQ carveout: keep "annotation_quality redefined in 2026-05 KG release; min_quality semantics shifted; see docs://guide/conventions" as 1 line in the relevant Pydantic field description and as 1 line in `mistakes:`.**
- [ ] **Step 4: Edit `gene_details`** — same as Step 3 re: AQ carveout.
- [ ] **Step 5: Edit `genes_by_function`** — same AQ carveout. Cross-link Lucene-syntax explanation to `docs://guide/conventions`.
- [ ] **Step 6: Edit `list_organisms`** — drop stamped counts; keep tool-specific `by_measurement_capability` semantics.
- [ ] **Step 7: Edit `list_publications`** — drop stamped counts; preserve metabolomics-publication tool-specific note.
- [ ] **Step 8: Edit `list_experiments`** — drop stamped counts; **keep** the tool-specific `table_scope` interaction with tested-absent rows (rule 9 carveout for tool-specific deviations).
- [ ] **Step 9: Edit `list_filter_values`** — apply the rules; expect minimal changes.

- [ ] **Step 10: Full regenerate as a sanity pass**

```bash
uv run python scripts/build_about_content.py
```

This rebuilds every tool with input YAML. Confirms no bleed-through (Pydantic models shared across tools — e.g. `MetaboliteResult` reused — would otherwise show up in unexpected tool md if a description got re-edited).

- [ ] **Step 11: Lint check the 9 batch-1 md files**

```bash
grep -nE '\d{4}-\d{2}-\d{2}| today\b|Phase [0-9]|§|\baudit\b|KG-[A-Z]+-[0-9]|F[0-9] |D[0-9] |Mode-[A-Z]|Cluster [A-Z]|parent §' \
  multiomics_explorer/skills/multiomics-kg-guide/references/tools/{kg_schema,resolve_gene,gene_overview,gene_details,genes_by_function,list_organisms,list_publications,list_experiments,list_filter_values}.md \
  | grep -v -E '\[AQ\]|\[ENR\]|annotation_quality|informative_only'
```

Expected: empty output. Fix any source-side hits and re-run Step 10.

- [ ] **Step 12: Smoke test**

```bash
pytest tests/unit/ -q
```

Expected: all green.

- [ ] **Step 13: Commit Batch 1**

```bash
git status   # confirm only tools.py, 9 yamls, 9 md files staged

git add multiomics_explorer/mcp_server/tools.py \
        multiomics_explorer/inputs/tools/{kg_schema,resolve_gene,gene_overview,gene_details,genes_by_function,list_organisms,list_publications,list_experiments,list_filter_values}.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/{kg_schema,resolve_gene,gene_overview,gene_details,genes_by_function,list_organisms,list_publications,list_experiments,list_filter_values}.md

git commit -m "$(cat <<'EOF'
docs(mcp): readability pass batch 1 — discovery + identity

9 tools: kg_schema, resolve_gene, gene_overview, gene_details,
genes_by_function, list_organisms, list_publications, list_experiments,
list_filter_values. Drops time-stamped counts, internal-history
shorthand, and multi-paragraph re-explanations of cross-cutting
semantics already covered in docs://guide/*. AQ drift markers kept
inline as 1-line carveouts on affected tools. No behavior change.

Spec: docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
Plan: docs/superpowers/plans/2026-05-07-mcp-docs-readability-pass.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Batch 2 — chemistry + metabolomics (7 tools)

**Files (edit per tool, regenerate, commit once at end):**
- Modify: `multiomics_explorer/mcp_server/tools.py` (functions + Pydantic models)
- Modify: `multiomics_explorer/inputs/tools/{list_metabolite_assays,genes_by_metabolite,metabolites_by_gene,metabolites_by_quantifies_assay,metabolites_by_flags_assay,assays_by_metabolite}.yaml`
- Regenerated: corresponding 6 md files (note: `list_metabolites` already done in Task 0 — not re-edited here).

Tools: `list_metabolite_assays`, `genes_by_metabolite`, `metabolites_by_gene`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`. (`list_metabolites` done in Task 0.)

This batch is the densest in violations (per the audit). Common patterns:
- "F1 informativeness", "Phase 5", "Phase 1 plumbing", "audit §4.3.3", "parent §10", "(audit §4.3.3 primary headline)" — drop all.
- "tested-absent rows are real biology" — currently restated in 6 places. Cross-link to `docs://guide/conventions` from docstrings; keep in field descriptions as 1 clause.
- "transport-confidence" — currently has 2-paragraph explanations in `genes_by_metabolite` and `metabolites_by_gene`. Cross-link to `docs://guide/conventions` from docstrings; keep `substrate_confirmed` / `family_inferred` 1-clause definitions on the field.
- `family_inferred`-dominance auto-warning — keep, it's behavior.

- [ ] **Step 1: Edit `list_metabolite_assays`**

Audit + apply 9 rules. Specific:
- "audit §4.3.3 primary headline — 75% of numeric edges are `not_detected`" → drop the audit ref. Keep the 75% (it's a stable structural fact about the data layer, not a count of nodes).
- "Phase 5", "(D3 sentinel-stripped)" → drop.
- "metabolite_count_total (cumulative across assays — see field-rubric note)" → drop the "field-rubric note" pointer; keep "cumulative across assays".

Edit `tools.py` + `inputs/tools/list_metabolite_assays.yaml`. Regenerate that tool.

- [ ] **Step 2: Edit `genes_by_metabolite`**

Apply 9 rules. Specific:
- Docstring: drop multi-paragraph "Auto-warning when family_inferred dominates" — make 1 line. Cross-link transport-confidence to `docs://guide/conventions`.
- Field descriptions: keep `evidence_source` and `transport_confidence` field-scoped semantics inline (rule 9 carveout for Pydantic).
- Drop "(rollup-extended)", "post-TCDB", "(family_inferred dominates by volume — per-gene median ≈ 6, p90 ≈ 90, max = 551 via the ABC superfamily)". The numeric medians are not stable — drop. The "ABC superfamily edge case" is a gotcha worth keeping but rephrased as: "Some genes annotated only to broad TCDB families (e.g. ABC transporters) emit large numbers of family_inferred rows."

Edit `tools.py` + YAML. Regenerate.

- [ ] **Step 3: Edit `metabolites_by_gene`**

Apply 9 rules. Specific:
- Docstring: drop "9 ABC-superfamily-only MED4 genes each emit 551 transport-arm family_inferred rows" — restate as: "Some genes (notably ABC-only annotations) emit large numbers of family_inferred rows; the global precision-tier sort prevents one gene from consuming `limit`."
- Drop "Workflow B'" reference. Drop "KG-MET-002". Drop "M2 follow-up".
- Cross-link the `top_metabolite_pathways` "chemistry-pathway filtered by `KeggTerm.reaction_count >= 3`" to `docs://analysis/metabolites` if it's a multi-paragraph passage; keep 1 clause if it's one line.

Edit `tools.py` + YAML. Regenerate.

- [ ] **Step 4: Edit `metabolites_by_quantifies_assay`**

Apply 9 rules. Specific:
- Drop "(audit §4.3.3 primary headline)", "(parent §10)", "per parent §13.6" — all internal-history shorthand.
- "75% of numeric edges are not_detected" — keep (structural fact).
- Cross-link tested-absent prose to `docs://guide/conventions`.

Edit `tools.py` + YAML. Regenerate.

- [ ] **Step 5: Edit `metabolites_by_flags_assay`**

Apply 9 rules. Specific:
- Drop "62% of boolean rows are `flag_value=false`" — actually, this 62% is structural and stable (it's the corpus shape, not a count of nodes). **Keep.** Border case — when in doubt, keep numeric biology shape, drop counts of nodes.
- "(unlike `genes_by_boolean_metric` which returns 0 rows for `False` per DM positive-only storage)" — keep, this is a tool-specific deviation worth inline (rule 9 carveout).
- Drop "Phase 5", "audit §", "parent §13.6".

Edit `tools.py` + YAML. Regenerate.

- [ ] **Step 6: Edit `assays_by_metabolite`**

Apply 9 rules. Specific:
- Drop "parallels Phase 3 `genes_by_metabolite`" — tool-cross-reference is fine, "Phase 3" tag isn't.
- Drop "(D2 closure)".
- Cross-link tested-absent + cross-arm-padding semantics if multi-paragraph.

Edit `tools.py` + YAML. Regenerate.

- [ ] **Step 7: Full regenerate**

```bash
uv run python scripts/build_about_content.py
```

- [ ] **Step 8: Lint check batch-2 md files**

```bash
grep -nE '\d{4}-\d{2}-\d{2}| today\b|Phase [0-9]|§|\baudit\b|KG-[A-Z]+-[0-9]|F[0-9] |D[0-9] |Mode-[A-Z]|Cluster [A-Z]|parent §' \
  multiomics_explorer/skills/multiomics-kg-guide/references/tools/{list_metabolite_assays,genes_by_metabolite,metabolites_by_gene,metabolites_by_quantifies_assay,metabolites_by_flags_assay,assays_by_metabolite}.md \
  | grep -v -E '\[AQ\]|\[ENR\]|annotation_quality|informative_only'
```

Expected: empty.

- [ ] **Step 9: Smoke test**

```bash
pytest tests/unit/ -q
```

Expected: green.

- [ ] **Step 10: Commit Batch 2**

```bash
git add multiomics_explorer/mcp_server/tools.py \
        multiomics_explorer/inputs/tools/{list_metabolite_assays,genes_by_metabolite,metabolites_by_gene,metabolites_by_quantifies_assay,metabolites_by_flags_assay,assays_by_metabolite}.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/{list_metabolite_assays,genes_by_metabolite,metabolites_by_gene,metabolites_by_quantifies_assay,metabolites_by_flags_assay,assays_by_metabolite}.md

git commit -m "$(cat <<'EOF'
docs(mcp): readability pass batch 2 — chemistry + metabolomics

6 tools: list_metabolite_assays, genes_by_metabolite,
metabolites_by_gene, metabolites_by_quantifies_assay,
metabolites_by_flags_assay, assays_by_metabolite.
(list_metabolites done separately in template commit.)
Drops audit §-refs, Phase-N tags, KG-MET-* shorthand. Cross-links
tested-absent and transport-confidence multi-paragraph prose to
docs://guide/conventions. No behavior change.

Spec: docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
Plan: docs/superpowers/plans/2026-05-07-mcp-docs-readability-pass.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Batch 3 — DE / DM / orthology / clustering (14 tools)

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Modify: `multiomics_explorer/inputs/tools/{differential_expression_by_gene,differential_expression_by_ortholog,gene_response_profile,list_derived_metrics,gene_derived_metrics,genes_by_numeric_metric,genes_by_boolean_metric,genes_by_categorical_metric,gene_homologs,search_homolog_groups,genes_by_homolog_group,gene_clusters_by_gene,genes_in_cluster,list_clustering_analyses}.yaml`
- Regenerated: 14 md files

Tools: `differential_expression_by_gene`, `differential_expression_by_ortholog`, `gene_response_profile`, `list_derived_metrics`, `gene_derived_metrics`, `genes_by_numeric_metric`, `genes_by_boolean_metric`, `genes_by_categorical_metric`, `gene_homologs`, `search_homolog_groups`, `genes_by_homolog_group`, `gene_clusters_by_gene`, `genes_in_cluster`, `list_clustering_analyses`.

Common patterns this batch:
- DM family gating prose (rankable-gated, has_p_value-gated, soft-exclude semantics) — covered in `docs://guide/conventions`. Cross-link from docstring; 1-clause inline on field descriptions.
- "table_scope" tested-absent interaction on DE tools — keep (tool-specific deviation, rule 9 carveout).
- "DM positive-only storage" gotcha on `genes_by_boolean_metric` — keep, tool-specific.
- "excluded_derived_metrics / warnings always [] — kept for cross-tool envelope-shape consistency" — drop the explanation; keep the field exist note.

- [ ] **Step 1: Edit `differential_expression_by_gene`** — keep `table_scope` tool-specific gotcha; drop time-stamps; cross-link DE-direction prose to `docs://guide/conventions`.
- [ ] **Step 2: Edit `differential_expression_by_ortholog`** — same; drop "Mode-B template" refs.
- [ ] **Step 3: Edit `gene_response_profile`** — likely terse. Drop time-stamps.
- [ ] **Step 4: Edit `list_derived_metrics`** — `[ENR]` does NOT apply here. Cross-link DM family gating to `docs://guide/conventions`. Drop "DM slice-2", "Phase X" tags.
- [ ] **Step 5: Edit `gene_derived_metrics`** — same.
- [ ] **Step 6: Edit `genes_by_numeric_metric`** — keep tool-specific rankable-gated soft-exclude semantics on the relevant Pydantic field. Cross-link the rest.
- [ ] **Step 7: Edit `genes_by_boolean_metric`** — keep "DM positive-only storage" as 1-clause tool-specific gotcha. Cross-link rest.
- [ ] **Step 8: Edit `genes_by_categorical_metric`** — same.
- [ ] **Step 9: Edit `gene_homologs`** — likely terse.
- [ ] **Step 10: Edit `search_homolog_groups`** — likely terse.
- [ ] **Step 11: Edit `genes_by_homolog_group`** — likely terse.
- [ ] **Step 12: Edit `gene_clusters_by_gene`** — likely terse.
- [ ] **Step 13: Edit `genes_in_cluster`** — likely terse.
- [ ] **Step 14: Edit `list_clustering_analyses`** — likely terse.

- [ ] **Step 15: Full regenerate**

```bash
uv run python scripts/build_about_content.py
```

- [ ] **Step 16: Lint check batch-3 md files**

```bash
grep -nE '\d{4}-\d{2}-\d{2}| today\b|Phase [0-9]|§|\baudit\b|KG-[A-Z]+-[0-9]|F[0-9] |D[0-9] |Mode-[A-Z]|Cluster [A-Z]|parent §' \
  multiomics_explorer/skills/multiomics-kg-guide/references/tools/{differential_expression_by_gene,differential_expression_by_ortholog,gene_response_profile,list_derived_metrics,gene_derived_metrics,genes_by_numeric_metric,genes_by_boolean_metric,genes_by_categorical_metric,gene_homologs,search_homolog_groups,genes_by_homolog_group,gene_clusters_by_gene,genes_in_cluster,list_clustering_analyses}.md \
  | grep -v -E '\[AQ\]|\[ENR\]|annotation_quality|informative_only'
```

Expected: empty.

- [ ] **Step 17: Smoke test**

```bash
pytest tests/unit/ -q
```

Expected: green.

- [ ] **Step 18: Commit Batch 3**

```bash
git add multiomics_explorer/mcp_server/tools.py \
        multiomics_explorer/inputs/tools/{differential_expression_by_gene,differential_expression_by_ortholog,gene_response_profile,list_derived_metrics,gene_derived_metrics,genes_by_numeric_metric,genes_by_boolean_metric,genes_by_categorical_metric,gene_homologs,search_homolog_groups,genes_by_homolog_group,gene_clusters_by_gene,genes_in_cluster,list_clustering_analyses}.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/{differential_expression_by_gene,differential_expression_by_ortholog,gene_response_profile,list_derived_metrics,gene_derived_metrics,genes_by_numeric_metric,genes_by_boolean_metric,genes_by_categorical_metric,gene_homologs,search_homolog_groups,genes_by_homolog_group,gene_clusters_by_gene,genes_in_cluster,list_clustering_analyses}.md

git commit -m "$(cat <<'EOF'
docs(mcp): readability pass batch 3 — DE / DM / orthology / clustering

14 tools: differential_expression_by_gene/ortholog,
gene_response_profile, list_derived_metrics, gene_derived_metrics,
genes_by_{numeric,boolean,categorical}_metric, gene_homologs,
search_homolog_groups, genes_by_homolog_group, gene_clusters_by_gene,
genes_in_cluster, list_clustering_analyses. Drops Phase-N tags,
slice/audit refs, time-stamped counts. Cross-links DM family gating
and DE direction prose to docs://guide/conventions. table_scope
tested-absent interaction kept inline (tool-specific). DM positive-only
storage gotcha kept inline on genes_by_boolean_metric. No behavior change.

Spec: docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
Plan: docs/superpowers/plans/2026-05-07-mcp-docs-readability-pass.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Batch 4 — ontology + enrichment + cypher (7 tools)

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Modify: `multiomics_explorer/inputs/tools/{search_ontology,ontology_landscape,genes_by_ontology,gene_ontology_terms,pathway_enrichment,cluster_enrichment,run_cypher}.yaml`
- Regenerated: 7 md files

Tools: `search_ontology`, `ontology_landscape`, `genes_by_ontology`, `gene_ontology_terms`, `pathway_enrichment`, `cluster_enrichment`, `run_cypher`.

Common patterns this batch:
- `[ENR]` carveout per rule 3 — keep "informative_only=True default as of 2026-05" as 1-line on `pathway_enrichment` and `cluster_enrichment`.
- BRITE-tree-must-scope explanation — covered in `docs://guide/conventions`. Cross-link from docstrings; 1-clause on `tree=` Field description.
- Hierarchy `level` convention — covered in `docs://guide/conventions`. Cross-link multi-paragraph; 1-clause on field.
- Background semantics for enrichment — covered in `docs://guide/conventions` AND in `docs://analysis/enrichment`. Cross-link from docstrings; 1-clause on `background=` Field description.

- [ ] **Step 1: Edit `search_ontology`** — cross-link Lucene + level convention to `docs://guide/conventions`. Drop time-stamps.
- [ ] **Step 2: Edit `ontology_landscape`** — similar; drop "Cluster A" tag.
- [ ] **Step 3: Edit `genes_by_ontology`** — cross-link three-modes prose (`term_ids` only, `level` only, both — DOWN expand vs UP rollup vs scoped) to `docs://guide/conventions`. Keep 1-clause on `term_ids` Field (rule 9 carveout). `[AQ]` does not apply here directly, but if a description currently mentions AQ, keep 1-line carveout.
- [ ] **Step 4: Edit `gene_ontology_terms`** — similar. Cross-link "leaf" vs "rollup" mode prose if multi-paragraph.
- [ ] **Step 5: Edit `pathway_enrichment`** — `[ENR]` carveout: keep 1-line "informative_only=True default as of 2026-05; pass informative_only=False for pre-2026-05 baseline; see docs://guide/conventions" inline. Cross-link Fisher+BH methodology to `docs://analysis/enrichment` (already done in current docs — verify).
- [ ] **Step 6: Edit `cluster_enrichment`** — same `[ENR]` carveout.
- [ ] **Step 7: Edit `run_cypher`** — likely terse. Drop time-stamps.

- [ ] **Step 8: Full regenerate**

```bash
uv run python scripts/build_about_content.py
```

- [ ] **Step 9: Lint check batch-4 md files**

```bash
grep -nE '\d{4}-\d{2}-\d{2}| today\b|Phase [0-9]|§|\baudit\b|KG-[A-Z]+-[0-9]|F[0-9] |D[0-9] |Mode-[A-Z]|Cluster [A-Z]|parent §' \
  multiomics_explorer/skills/multiomics-kg-guide/references/tools/{search_ontology,ontology_landscape,genes_by_ontology,gene_ontology_terms,pathway_enrichment,cluster_enrichment,run_cypher}.md \
  | grep -v -E '\[AQ\]|\[ENR\]|annotation_quality|informative_only'
```

Expected: empty.

- [ ] **Step 10: Smoke test**

```bash
pytest tests/unit/ -q
```

Expected: green.

- [ ] **Step 11: Commit Batch 4**

```bash
git add multiomics_explorer/mcp_server/tools.py \
        multiomics_explorer/inputs/tools/{search_ontology,ontology_landscape,genes_by_ontology,gene_ontology_terms,pathway_enrichment,cluster_enrichment,run_cypher}.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/{search_ontology,ontology_landscape,genes_by_ontology,gene_ontology_terms,pathway_enrichment,cluster_enrichment,run_cypher}.md

git commit -m "$(cat <<'EOF'
docs(mcp): readability pass batch 4 — ontology + enrichment + cypher

7 tools: search_ontology, ontology_landscape, genes_by_ontology,
gene_ontology_terms, pathway_enrichment, cluster_enrichment, run_cypher.
Cross-links BRITE-tree, hierarchy level, and Fisher+BH methodology
prose to docs://guide/conventions and docs://analysis/enrichment.
[ENR] informative_only drift marker kept inline on pathway_enrichment
and cluster_enrichment per rule-3 carveout. No behavior change.

Spec: docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
Plan: docs/superpowers/plans/2026-05-07-mcp-docs-readability-pass.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Final pass — guides contradiction sweep + tree-wide lint

**Files:**
- Read-only: `multiomics_explorer/skills/multiomics-kg-guide/references/guide/{start_here,concepts,conventions,python_api}.md` — verify no contradictions opened up.
- Read-only: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md` — full-tree lint.
- (Likely) no changes needed; this task is primarily verification.

- [ ] **Step 1: Full-tree lint**

```bash
grep -nE '\d{4}-\d{2}-\d{2}| today\b|Phase [0-9]|§|\baudit\b|KG-[A-Z]+-[0-9]|F[0-9] |D[0-9] |Mode-[A-Z]|Cluster [A-Z]|parent §' \
  multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md \
  | grep -v -E '\[AQ\]|\[ENR\]|annotation_quality|informative_only'
```

Expected: empty. The 138 raw violations measured before the pass should all be either fixed or under the AQ/ENR carveout exclusion.

If anything surfaces:
- Fix at the source (`tools.py` or YAML).
- Re-run `uv run python scripts/build_about_content.py`.
- Re-run the lint.
- Repeat until empty.

- [ ] **Step 2: Tally per-rule**

For visibility, surface what was kept under carveout:

```bash
grep -nE '\[AQ\]|\[ENR\]|annotation_quality|informative_only' \
  multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md
```

Expected: hits on `gene_overview.md`, `gene_details.md`, `genes_by_function.md`, `pathway_enrichment.md`, `cluster_enrichment.md` (plus the 4 ontology tools that mention `informative_only`). All should be 1-line drift markers, not multi-paragraph re-explanations.

- [ ] **Step 3: Spot-check the three densest pages by hand**

```bash
wc -l multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolites.md \
       multiomics_explorer/skills/multiomics-kg-guide/references/tools/pathway_enrichment.md \
       multiomics_explorer/skills/multiomics-kg-guide/references/tools/genes_by_metabolite.md
```

Compare to pre-pass line counts:
- `list_metabolites.md`: was 235 lines → expected ≤ 200 lines.
- `pathway_enrichment.md`: pre-pass count → expected ~10-20% reduction.
- `genes_by_metabolite.md`: pre-pass count → expected ~10-20% reduction.

Reduction targets are soft — the goal is rule compliance, not line count. But significant *increase* would suggest accidental content addition.

Open each in an editor and read top-to-bottom. Confirm:
- "What it does" is ≤ 6 lines.
- Params table descriptions are ≤ 2 sentences each.
- "Common mistakes" / "Good to know" has no duplicates of field-description content.
- Cross-links use `docs://...` URIs only; no `§`, `Phase N`, `audit` refs.

- [ ] **Step 4: Verify the four guide files weren't touched**

```bash
git status multiomics_explorer/skills/multiomics-kg-guide/references/guide/
```

Expected: clean. The guides are out of scope unless a contradiction was found. If a guide was touched mid-batch (e.g. you discovered a guide claim was wrong), call that out in the final commit.

- [ ] **Step 5: Verify CLAUDE.md was not touched**

```bash
git status CLAUDE.md
```

Expected: clean. CLAUDE.md tool table is internal-team, out of scope per spec.

- [ ] **Step 6: Final smoke test**

```bash
pytest tests/unit/ -q
```

Expected: green. (No code changed across the whole pass — only docstrings + Pydantic descriptions + YAML — but the smoke test catches any syntactic accidents.)

- [ ] **Step 7: Optional — sanity-check the MCP server can start**

```bash
uv run python -c "from fastmcp import FastMCP; from multiomics_explorer.mcp_server.tools import register_tools; mcp = FastMCP('test'); register_tools(mcp); import asyncio; print(len(asyncio.run(mcp.list_tools())), 'tools registered')"
```

Expected: `37 tools registered`.

- [ ] **Step 8: Push reminder (do NOT push without explicit user OK)**

The user gates pushes manually. After Task 5 passes:

> "Readability pass complete. 5 commits ahead of origin (Task 0 + Batches 1–4). Want me to push?"

Wait for explicit OK before `git push`.

---

## Notes for the executing engineer

1. **The 9 rules are mechanical, but applying them requires reading the rendered md.** Don't try to apply them by editing `tools.py` blind — open the rendered md in parallel. The Pydantic field description becomes a row in the params table; if the row reads badly in markdown, edit the description.

2. **Behavior is sacred.** This pass is documentation only. If you find a description that says X but the code does Y, fix the description, don't touch the code. If the code is wrong, file it as a follow-up; don't silently fix it in this pass. (The exception is typos that don't change semantics — those are fine.)

3. **The lint regex is conservative.** It will not catch every style violation — e.g. it won't catch a multi-paragraph re-explanation of "tested-absent" that doesn't use any of the flagged tokens. The lint is a safety net, not a sufficient check. The primary check is reading the regenerated md against the 9 rules.

4. **`scripts/build_about_content.py` writes directly to the served path** — there is no separate sync step. Running it after every per-tool edit gives you the rendered md immediately. The script accepts a single tool name argument for fast iteration: `uv run python scripts/build_about_content.py list_metabolites`.

5. **YAML is YAML** — quote anything starting with `*`, `:`, `?`, `!`, `&`, `|`. The existing files already do this where needed; follow the established pattern.

6. **The conventions guide (`docs://guide/conventions`) is the most important cross-link target.** Most rule-9 deferrals go there. Read it once before starting Task 1 so you know exactly what semantics it covers and where to point.

7. **Cross-tool Pydantic models are shared** (e.g. multiple tools use `MetaboliteResult`). Editing the field description on a shared model affects every tool using it. Run the full regenerate (Step 10 of each batch) to confirm no surprise edits in tool md files outside the current batch.

---

## Self-review summary

**Spec coverage:** every rule (1–9) is referenced in either Task 0 (template), Task 1–4 (per-batch), or Task 5 (final lint). The rule-3 `[AQ]`/`[ENR]` carveouts have explicit per-tool steps. The rule-9 inline carveouts (Pydantic field descriptions, 1-line YAML gotchas) are called out in Task 0 Step 4 and reapplied per-batch. The "no behavior change" rule is restated in the engineer notes.

**Placeholder scan:** none. Every step has an exact command or exact text to apply. The "tool-specific spin" judgment calls (e.g. table_scope, transport-confidence) are explicitly enumerated in batch-task notes.

**Type / signature consistency:** none — this is a docs pass; no code identifiers introduced.

**Out-of-scope cleanliness:** spec correctly marks `kg/queries_lib.py`, `api/functions.py`, `CLAUDE.md`, `scripts/build_about_content.py`, the 4 guide files, and analysis md as out of scope. Plan respects all five.
