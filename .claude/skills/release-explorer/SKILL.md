---
name: release-explorer
description: Cut, build, verify, and publish a versioned multiomics-explorer release. Use when the user says "release the explorer", "cut an explorer alpha", "tag X.Y.Z", "/release-explorer <version>", or wants to produce a tagged GitHub Release with a verified wheel + sdist. Runs preflight → CHANGELOG cut (pauses for polish) → commit/tag/push → uv build + wheel verification (no leakage, LICENSE present, throwaway-venv import test) → publish GitHub Release with wheel/sdist/metadata.json as assets. Idempotent re-runs. `--dry-run` exercises every phase without mutating anything. PyPI publication is intentionally out of scope for v1 — install path is git tag.
argument-hint: <version> [--draft] [--dry-run] [--resume] [--allow-dirty]
user-invocable: true
allowed-tools: Read, Edit, Write, Bash(uv *), Bash(uv run *), Bash(python *), Bash(python3 *), Bash(git *), Bash(gh *), Bash(rm -rf /tmp/explorer-release-*)
---

# Release Explorer Skill

Cut a tagged GitHub Release of `multiomics_explorer`. Mirrors the KG repo's
`/release-kg` process spine (preflight → CHANGELOG cut → commit/tag/push →
build/verify → publish), simplified for a Python package: no Docker, no
blue/green deploys, no `Schema_info` stamping. The wheel + sdist are the
artifacts.

See `references/PHASES.md` here for phase-by-phase mechanics, and
`docs/superpowers/specs/2026-06-01-explorer-package-release-design.md`
for the underlying release design.

## When to use

Trigger phrasings: "release the explorer", "cut an explorer alpha",
"tag a release", "/release-explorer X.Y.Z", "produce an explorer release",
"publish v0.1.0".

Do **not** use for:
- Routine commits or PRs — this skill *cuts a release*, it doesn't just
  publish a wheel from the current HEAD.
- PyPI publication — out of scope today; install path is git tag.

## Args

| Arg | Default | Meaning |
|---|---|---|
| `<version>` | — | `X.Y.Z[-(alpha\|beta\|rc).N]` (without `v` prefix). Becomes git tag `v<version>`. Must match `pyproject.toml`'s `version` field. |
| `--draft` | off | Publish GitHub Release as draft (`gh release create --draft`). |
| `--dry-run` | off | Every phase logs `[dry-run] would <action>`; mutates nothing (no commits, tags, push, build, gh). Use to exercise the pipeline. |
| `--resume` | off | Skip the post-CHANGELOG-cut pause (use on the second invocation after polishing). |
| `--allow-dirty` | off | Skip the working-tree-clean and behind-origin checks. |

## Flow

Five phases, each idempotent. The default invocation **pauses once** —
after Phase 2 cuts the `CHANGELOG.md` `[Unreleased]` section — so the
operator can polish prose. Re-run with `--resume` to continue from commit
onward.

1. **Preflight** — version regex; `pyproject.toml` version matches arg;
   tooling (`uv` / `git` / `gh`) on PATH; `gh auth status` OK; git on a
   branch, working tree clean, in sync with origin; `pytest tests/unit/`
   green. Captures git SHA / branch / dirty into context.
2. **CHANGELOG cut** — rename `## [Unreleased]` → `## [<version>] - YYYY-MM-DD`,
   open a fresh empty `## [Unreleased]` above. Idempotent: if
   `## [<version>]` already exists, no-op. **Pauses for polish** unless
   `--resume` is set.
3. **Commit + tag + push** — `chore(release): v<version>` commit (CHANGELOG
   + pyproject), annotated tag `v<version>`, `git push --follow-tags`.
   Each step idempotent.
4. **Build + verify** — `uv build` produces wheel + sdist into `dist/`.
   Verify: no `inputs/`, `cli/`, `tests/`, `.env`, `.venv/` leakage in the
   wheel; LICENSE included; the wheel installs cleanly into a throwaway
   `uv venv` and `import multiomics_explorer` succeeds; the
   `multiomics-kg-mcp` console script is registered.
5. **Publish** — write `metadata.json` (version, git identity, artifact
   filenames, timestamps); extract the `[<version>]` CHANGELOG section to
   `.release-notes-<version>.md`; `gh release create v<version>
   --notes-file <fragment> [--prerelease] [--draft]` with the wheel +
   sdist + `metadata.json` attached as assets. Pre-release flag is
   automatic for any `X.Y.Z-<suffix>.N` version. Prints the install URL
   + a cross-repo coordination reminder (KG-side `Schema_info.mcp_min_version`).

## Examples

```bash
# Dry-run end-to-end — exercises every phase, mutates nothing
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1 --dry-run

# Real cut, pauses after CHANGELOG cut
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1

# (operator polishes CHANGELOG.md in $EDITOR)

# Resume after polish
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1 --resume

# Cut a draft (don't publish publicly yet)
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1 --draft
```

## What this skill does NOT do

- **PyPI publication.** Per release-design spec §2 / §11, PyPI is deferred;
  git-tag install (`uv add git+https://github.com/wosnat/multiomics_explorer.git@v<version>`)
  is the v1 path. When PyPI lands, it becomes a new Phase 6 (`uv publish`),
  not a flag here.
- **Version bump.** This skill assumes you've already bumped
  `pyproject.toml`'s `version` field to match the `<version>` arg. Preflight
  fails fast if they disagree — fix `pyproject.toml`, re-run.
- **Auto-fill changelog.** The operator writes the prose during the Phase-2
  pause. Stats (file counts, line counts) are NOT auto-injected — the
  changelog is for humans.
- **KG-side coordination.** When the explorer↔KG contract changes, the KG
  needs its own release with a bumped `Schema_info.mcp_min_version`. That
  coordination is documented in the changelog body and printed in the
  closing announcement, but it is not automated here. See KG plan §2.3.

## Gotchas

- **`pyproject.toml` version must match the arg.** Bump it BEFORE invoking
  the skill; otherwise preflight aborts. (Future enhancement: an interactive
  bump step.)
- **`--dry-run` only needs `git`** — preflight skips the `gh auth` check and
  any network calls when `--dry-run` is set. Real runs require `gh auth status`
  to pass.
- **`--resume` is your friend after the CHANGELOG pause** — re-running
  without it just re-prints "polished? rerun with --resume" because the
  script detects the cut is already done.
- **Idempotency cuts both ways** — re-running with the same version when
  the GitHub Release already exists will skip the commit/tag steps but
  `gh release create` will fail with "release already exists." That's
  intentional; bump the version or `gh release delete v<version>` first.
- **Branch behind origin** triggers a fatal preflight error. Pull (merge
  or rebase) before retrying.
- **PEP 440 wheel filenames.** `uv build` normalizes `0.1.0-alpha.1` to
  `0.1.0a1` in the wheel filename (`multiomics_explorer-0.1.0a1-py3-none-any.whl`).
  The git tag stays `v0.1.0-alpha.1`. This is expected — Python packaging
  and SemVer disagree on pre-release punctuation; the skill handles both.
