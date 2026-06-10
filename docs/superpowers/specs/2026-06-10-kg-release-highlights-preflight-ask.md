# Ask (KG-side): preflight release highlights on `Schema_info`

**Date:** 2026-06-10
**Status:** Draft ask for the KG team (`multiomics_biocypher_kg`).
**Audience:** KG release pipeline owner.
**Related:**
- [2026-06-02-kg-compatibility-check-design.md](2026-06-02-kg-compatibility-check-design.md) — the `kg_release_info` MCP tool this extends. It already reads `Schema_info { .* }` and surfaces identity + a compat verdict.
- KG `.claude/skills/release-kg/release_kg.py` — `extract_changelog_fragment()` (the per-version CHANGELOG section already rendered for GitHub notes) and the `Schema_info` stamping at build/import.

## 1. Goal — and what this is *not*

`kg_release_info` is a **user preflight**: a researcher points Claude Code at a KG, the MCP calls it once at startup, and the user gets oriented. This ask adds a human-readable **change list** to that preflight so the user can answer two questions *before they start working*:

1. **"What can I now ask that I couldn't before?"** — new capabilities / data layers in this KG release (e.g. publication discusses-edges, +N organisms, metabolomics layer).
2. **"Did anything change meaning under me?"** — semantics/breaking changes that silently alter the answers a user gets. The canonical example is the `annotation_quality` redefinition (0..3 numeric encoding), where existing `min_quality` filters silently shifted meaning with **no error**.

**Explicit non-goal:** this is *not* an explorer-development / schema-diff aid. We are **not** asking for a structured, machine-readable label/property delta to predict broken test fixtures. That is dev tooling for a different audience. Keep this human, short, and preflight-focused.

## 2. The two fields

Stamp two **optional string** properties on the `Schema_info` node at build/import time:

| Property | Content | Audience question answered |
|---|---|---|
| `release_highlights` | Short markdown bullets: the user-facing capability/data changes in this release. The "what's new you can now ask about." | "What can I now ask?" |
| `breaking_changes` | Short markdown bullets: semantics changes that alter results without erroring (redefinitions, renamed/repurposed fields, default-behavior flips). Empty/absent when none. | "Did anything change under me?" |

Both nullable. A KG built without them (or a legacy KG) → explorer surfaces nothing extra; no behavior change. `breaking_changes` is the higher-value field — it is the one most likely to be omitted if left implicit, and the one a user most needs at preflight.

## 3. Why this is cheap

- **Explorer side is pure passthrough.** The compat query already returns `Schema_info { .* }`, so both new properties arrive over the wire with **zero query change**. The only explorer work is adding two optional fields to the `KGIdentity` Pydantic model and rendering them in the `kg_release_info` summary. (Tracked separately as the explorer-side follow-up; trivial.)
- **The KG already extracts the per-version CHANGELOG section** (`extract_changelog_fragment()` for GitHub notes). The new strings can be sourced the same way.

## 4. The one real design decision: don't pipe the raw CHANGELOG section

Piping the raw `## [version]` section would bury the signal. The current `[Unreleased]` section's entire `Fixed` block is `/release-kg` deploy-tooling bugs — correct to log, useless to a user at preflight. So **do not** stamp the whole fragment.

**Proposed CHANGELOG convention** (KG team's call on exact spelling): within each version section, author two dedicated, preflight-facing subsections at cut time, e.g.:

```markdown
## [0.1.0-alpha.6] - 2026-06-XX

### Preflight: Highlights
- Publication "discusses" edges — ask "which papers discuss gene/pathway X?"
- +8 organisms incl. marine Synechococcus clades.

### Preflight: Breaking
- `annotation_quality` redefined to a 0..3 numeric encoding of
  `annotation_state`; existing `min_quality` filters silently shift meaning.

### Added
... (internal/full detail, NOT stamped)
### Fixed
... (release-tooling noise, NOT stamped)
```

At build/import, stamp `Schema_info.release_highlights` = the `Preflight: Highlights` body and `Schema_info.breaking_changes` = the `Preflight: Breaking` body. Absent subsection → null property. This keeps the preflight signal-dense and leaves the full changelog untouched for its existing role.

**Alternative if a CHANGELOG convention is unwanted:** pass the two strings explicitly into the build env (`KG_RELEASE_HIGHLIGHTS` / `KG_RELEASE_BREAKING`, analogous to the existing `KG_RELEASE_VERSION` stamping path) and have the release operator author them at cut time. Either mechanism is fine — the KG team owns the source.

## 5. Acceptance

- A KG built from a release whose CHANGELOG has the two subsections exposes non-null `Schema_info.release_highlights` / `Schema_info.breaking_changes`.
- A release with no breaking items leaves `breaking_changes` null/empty (not an empty-string artifact that renders as a blank bullet).
- A legacy KG (no subsections / no `Schema_info`) is unaffected — explorer preflight degrades silently, exactly as today.
- The full `## [version]` CHANGELOG section and GitHub Release notes are unchanged in role.

## 6. Open questions for the KG team

1. CHANGELOG-convention extraction vs. explicit env-var stamping — which fits `release_kg.py` better?
2. Subsection naming (`### Preflight: Highlights` / `### Preflight: Breaking` vs. `### Highlights` / `### Breaking`).
3. Length guidance — cap at ~5 bullets each so the preflight stays scannable?
