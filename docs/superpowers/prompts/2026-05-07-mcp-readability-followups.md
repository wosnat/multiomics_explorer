# Follow-up prompt: MCP outfacing-docs readability — propagation work

**Context — just-landed work (do NOT redo):**

Between commits `1a7d708` (spec+plan) and `4ee7504` (Batch 4) on `main`, a 6-commit pass reworked all 37 MCP tool outfacing surfaces (tool docstrings + Pydantic `Field(description=...)` strings + per-tool YAMLs) per 9 style rules:

1. No time-stamped counts (drop "149 today", keep structural ratios like "75% not_detected").
2. No internal-history shorthand (drop §, Phase N, audit §, F1/D2/D8, KG-XXX-NNN, Mode-B, Cluster A, parent §, slice-N, Workflow B').
3. No release-date hedges, **except `[AQ]` and `[ENR]` drift markers** kept as 1-line inline notes on affected tools.
4. Cross-link only by stable URI (`docs://guide/*`, `docs://analysis/*`, peer tool names).
5. De-duplicate — one canonical home per fact.
6. Pydantic field descriptions terse — lead = type/semantics; ≤ 1 example; no narrative.
7. Docstrings tight — ≤ 6 lines for simple tools; up to 22 lines for tools with multi-arm/polymorphic semantics.
8. CLAUDE.md tool table out of scope (separate task).
9. Defer cross-cutting prose to `docs://guide/conventions` — but Pydantic field descriptions ALWAYS restate inline, and 1-line YAML gotchas stay inline.

Spec: [docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md](../specs/2026-05-07-mcp-docs-readability-pass-design.md). Plan: [docs/superpowers/plans/2026-05-07-mcp-docs-readability-pass.md](../plans/2026-05-07-mcp-docs-readability-pass.md).

Net: -330 lines across 65 files; 138 lint-regex hits → 0 (modulo carveouts); pytest 2231 passed; all 37 tools register cleanly.

This prompt covers 3 follow-up items that should propagate the work back into the repo's developer-facing assets so the next tool addition is born compliant rather than needing another readability pass.

---

## Follow-up 1 — Add `--lint` mode to `scripts/build_about_content.py`

**Goal:** make the lint regex from the readability pass executable as a one-shot script invocation, so anyone editing `tools.py` or `inputs/tools/*.yaml` can verify their work locally before commit. Optional follow-up: wire into a pre-commit hook.

**Spec:**
- Add `--lint` flag to `scripts/build_about_content.py` (existing argparse already accepts `--all`, `--skeleton`, positional tool names).
- When `--lint` is set, after generation (or instead of it — your call), scan all `multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md` files and surface style-rule violations.
- Use the tightened lint regex (with `\b` word boundaries to avoid `MED4` / `Cluster IDs` false-positives):

  ```python
  LINT_PATTERN = (
      r'\d{4}-\d{2}-\d{2}'   # ISO date
      r'| today\b'            # stale "today" count
      r'|Phase [0-9]'         # internal phase tag
      r'|§'                   # cross-ref shorthand
      r'|\baudit\b'           # internal audit ref
      r'|KG-[A-Z]+-[0-9]'     # KG-XXX-NNN ticket ID
      r'|\bF[0-9]\b'          # F1/F2/F3 internal slice tag
      r'|\bD[0-9]\b'          # D2/D8 internal slice tag
      r'|Mode-[A-Z]\b'        # Mode-A / Mode-B template tag
      r'|Cluster [A-Z]\b'     # Cluster A / Cluster B internal tag
      r'|parent §'            # cross-ref shorthand
  )

  CARVEOUT_PATTERN = r'\[AQ\]|\[ENR\]|annotation_quality|informative_only'
  ```

- For each violation: print `{file}:{line}: {matched-line-snippet}` and the rule that fired.
- Exit code 0 if clean (after carveout exclusion), non-zero if any violations remain — so it can be wired into pre-commit.
- Optionally accept tool name args to scope the lint to specific files: `uv run python scripts/build_about_content.py --lint list_metabolites pathway_enrichment`.

**Files:**
- Modify: `scripts/build_about_content.py` (add `--lint` mode + the regex constants).

**Done definition:**
- `uv run python scripts/build_about_content.py --lint` returns exit 0 today (post-readability-pass).
- Re-introducing a violation (e.g. add `# spec §6.6` to a Pydantic field description, regenerate) makes the lint exit non-zero with a clear file:line message.
- README or `--help` text mentions the new mode.

**Optional bonus:**
- A second mode `--lint-source` that scans `mcp_server/tools.py` and `inputs/tools/*.yaml` directly (in addition to rendered md), so the lint catches violations in source comments / YAML strings before regeneration.

---

## Follow-up 2 — Update `.claude/skills/add-or-update-tool/`

**Goal:** the skill that orchestrates new-tool work should bake in the 9 style rules so new tools are born compliant. Currently the skill (per `CLAUDE.md`) covers Phase 1 (scope + KG iteration + Cypher verification) and Phase 2 (parallel TDD build with file-owned agents) — neither phase teaches the agent the outfacing-doc style.

**Files to read first** (the existing skill source):
- `.claude/skills/add-or-update-tool/SKILL.md`
- `.claude/skills/add-or-update-tool/references/` (whatever supporting docs exist)
- `docs/superpowers/specs/2026-05-03-add-or-update-tool-redesign.md` (the design that produced the current skill)

**Spec — additions to the skill:**

1. **New section in SKILL.md** titled "Outfacing-doc style rules" (or fold into the existing Layer 3 / Layer 4 sections). Embed the 9 rules verbatim from the readability-pass spec at `docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md`. Cross-link to the spec for full rationale.

2. **Per-rule reminders inline at the relevant phase steps:**
   - When the agent is writing a tool docstring → quote rule 7 (≤ 6 lines for simple; up to 22 for multi-arm).
   - When writing Pydantic field descriptions → quote rule 6 (terse; lead with type; ≤ 1 example; no narrative).
   - When writing YAML mistakes → quote rule 5 (one canonical home per fact — don't restate Pydantic field descriptions).
   - When the agent reaches for "(introduced in Phase X)" or "(KG release 2026-05-06)" or numerical counts that may go stale → quote rules 1, 2, 3 (drop time-stamps, history shorthand, release-date hedges).

3. **`[AQ]` / `[ENR]` carveout note.** If a new tool surfaces a parameter or field affected by the May 2026 KG-release default flips (`min_quality` semantics, `informative_only` default), the skill should remind the agent to add the 1-line drift marker inline (Pydantic field + YAML mistake) per rule 3 carveout.

4. **Final step in the build phase:** add a "lint-before-commit" reminder that runs `uv run python scripts/build_about_content.py --lint {tool_name}` after regeneration (assumes Follow-up 1 is shipped). If the lint surfaces violations, the agent fixes the source and re-runs before declaring done.

5. **Code-review checklist update.** The skill currently dispatches a code reviewer at end of Phase 2. Add to the reviewer's checklist:
   - "Does the tool docstring open with an action verb and end with a `Routing: ` sentence?"
   - "Are Pydantic field descriptions ≤ 250 chars (the tooltip ceiling)?"
   - "Are AQ / ENR drift markers (if applicable) 1-line inline, not multi-paragraph?"
   - "Do all `docs://...` cross-links resolve to existing files?"
   - "**Lint-extension watch:** did you spot a recurring stale-language pattern (internal shorthand, time-stamped count, dated reference, archaeology jargon) that the `--lint` regex did NOT flag? If yes, extend `LINT_PATTERN` in `scripts/build_about_content.py` and add a unit test in `tests/unit/test_lint_about_content.py` in the same PR — cite the source violation. The lint is non-exhaustive by design; new tool patterns extend it. Do NOT just delete the bad text without growing the regex — the next tool will reintroduce it. See the readability-pass spec section on `--lint` mode for the full extension contract."

**Done definition:**
- The 9 rules appear in the skill (verbatim or by section + cross-link).
- Each rule has an inline reminder at the phase step where it bites.
- Code-review checklist updated.
- (Optional) The skill's worked example (if any) regenerated against the new rules so it doubles as a template.

---

## Follow-up 3 — Update `.claude/skills/layer-rules/`

**Goal:** the layer-rules skill defines the 4-layer architecture (kg / api / mcp_server / skills). After the readability pass, the boundaries between Layer 3 (Pydantic field descriptions in tools.py) and Layer 4 (per-tool md from inputs/tools/*.yaml + Pydantic) are now stylistically governed by the 9 rules. The skill should reflect that.

**Files to read first:**
- `.claude/skills/layer-rules/SKILL.md`
- `.claude/skills/layer-rules/references/layer-boundaries.md`

**Spec — additions to the skill:**

1. **In the Layer 3 section** (`mcp_server/tools.py`), add: "Tool docstring + every `Field(description=...)` are agent-outfacing surfaces. They follow the 9 outfacing-doc rules — see `docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md`. Inline Python source comments (`# ...`) in tools.py are NOT outfacing and are exempt."

2. **In the Layer 4 section** (`skills/.../references/tools/*.md`), add:
   - "The rendered md is auto-generated from Layer 3 (Pydantic) + `inputs/tools/{tool}.yaml`. Never hand-edit the rendered md."
   - "The four guide files at `docs://guide/{start_here, concepts, conventions, python_api}` are the authoritative cross-cutting preamble. Per-tool docs cross-link to them rather than re-explain."
   - "When updating a tool, regenerate via `uv run python scripts/build_about_content.py {tool_name}` and verify with `--lint` before committing." (Assumes Follow-up 1 is shipped.)

3. **Add a small "Outfacing-doc surface map" subsection** clarifying which surfaces are user/agent-facing:

   | Source location | Outfacing? | Style rules apply? |
   |---|---|---|
   | `kg/queries_lib.py` docstrings | No (internal) | No |
   | `api/functions.py` docstrings | Indirect (Python API users) | Best-effort |
   | `mcp_server/tools.py` tool docstring | **Yes** (FastMCP `description`, agent sees at tool-listing) | Yes |
   | `mcp_server/tools.py` Pydantic `Field(description=...)` | **Yes** (params table + per-result table in rendered md) | Yes |
   | `mcp_server/tools.py` Python `# ...` comments | No | No |
   | `inputs/tools/*.yaml` examples / mistakes / chaining | **Yes** (rendered into md) | Yes |
   | `skills/.../references/tools/*.md` | Auto-generated | N/A — edit upstream |
   | `skills/.../references/guide/*.md` | **Yes** | Yes (but rarely edited) |
   | `skills/.../references/analysis/*.md` | **Yes** (hand-authored) | Yes (best-effort) |
   | `CLAUDE.md` tool table | No (internal-team) | No |

4. **Add a brief "When a per-tool edit reveals a guide is wrong" workflow note:** "Prefer fixing the per-tool side. Only edit a guide file if the per-tool truth contradicts the guide AND the guide is the authoritative claim. Guide edits are rare and warrant a separate explanatory commit."

5. **Add a 1-line note on lint extensibility** in the Layer 4 outfacing-rules subsection: "The `--lint` regex backstop in `scripts/build_about_content.py` is non-exhaustive by design — it encodes the shorthand patterns observed during the readability pass. When a new recurring stale-language pattern surfaces in tool work, extend `LINT_PATTERN` and add a unit test (don't suppress). See the readability-pass spec for the extension contract."

**Done definition:**
- Layer 3 / Layer 4 sections cross-link to the readability-pass spec.
- "Outfacing-doc surface map" table is present.
- Guide-edit workflow note is present.

---

## Cross-cutting — single commit per follow-up

Each of the 3 follow-ups is independent. Land each as a single commit:

```
feat(scripts): add --lint mode to build_about_content.py
docs(skill): bake 9 outfacing-doc rules into add-or-update-tool
docs(skill): add outfacing-surface map to layer-rules
```

After all 3 land, verify the loop closes by:
1. Running `uv run python scripts/build_about_content.py --lint` — exit 0.
2. Re-reading both updated skills and confirming the 9 rules + lint command are findable.

## Out of scope for this follow-up

- Re-running the readability pass on any tool (it's done; the 9 rules + the lint backstop the next maintenance cycle).
- The CLAUDE.md tool table cleanup (separate task — file as backlog if desired).
- Pre-commit hook wiring for the new `--lint` mode (separate task — needs a `.pre-commit-config.yaml` decision).
- The user-facing `multiomics_explorer.api.functions` docstrings — they flow through to package import users, not the agent surface this pass focused on. Could be a separate "docs(api)" task if desired.
