# `release-explorer` — Phase-by-phase reference

Detailed mechanics. See the parent `SKILL.md` for arg/usage summary and the
release-design spec
(`docs/superpowers/specs/2026-06-01-explorer-package-release-design.md`)
for the underlying decisions.

## Idempotency contract

Every phase is re-runnable. The script captures no state between invocations —
the state lives in the repo (`CHANGELOG.md`, git log, tags) and on disk
(`dist/`, `/tmp/explorer-release-check-<version>` venv). Re-running with the
same `<version>` either no-ops phases already done or reproduces them.

| Phase | Idempotent? | How |
|---|---|---|
| 1 Preflight | yes | Read-only |
| 2 CHANGELOG cut | yes | Skips if `## [<version>]` section already exists |
| 3 Commit/tag/push | yes | Skips commit if HEAD subject matches; skips tag if it exists; `git push` is naturally idempotent |
| 4 Build + verify | rebuild-heavy | Cleans `dist/` first; throwaway-venv check rebuilt each run. Read-only side effects. |
| 5 Publish | yes | `gh release create` fails fast if the release exists (intentional — bump version or `gh release delete` first). |

## Phase 1: Preflight

Fail-fast read-only checks, no mutation.

| Check | Failure mode | Override |
|---|---|---|
| Version matches `^\d+\.\d+\.\d+(-(alpha\|beta\|rc)\.\d+)?$` | exit 1 | — |
| `pyproject.toml` `version` field == `<version>` arg | exit 1 | bump `pyproject.toml`, re-run |
| Tools on PATH: `git`, `uv`, `gh` | exit 1 | install missing tool |
| `gh auth status` succeeds (real runs only; skipped under `--dry-run`) | exit 1 | run `gh auth login` |
| `git status --porcelain` is empty | exit 1 | `--allow-dirty` |
| `HEAD..origin/<branch>` count is 0 | exit 1 | `--allow-dirty`, or pull first |
| `pytest tests/unit/` green (skipped under `--dry-run`) | exit 1 | fix the failing test |

On success, captures `git_sha`, `git_sha_short`, `git_branch`, `git_dirty`,
`branch` into the run context — these flow into the publish manifest in
Phase 5.

## Phase 2: CHANGELOG cut

Uses the Keep-a-Changelog "accumulate-then-cut" model — mirrors KG's pattern
exactly.

- Reads `CHANGELOG.md` from the repo root.
- Locates `## [Unreleased]` (fatal if missing — the changelog has to be
  initialized).
- Captures the section body (everything until the next `## [` or EOF).
- Rewrites the file as:

```markdown
## [Unreleased]

### Added

### Changed

### Fixed

## [<version>] - <YYYY-MM-DD>

<the old Unreleased body, verbatim>
```

- **Idempotent:** if `## [<version>]` already exists anywhere in the file,
  the phase no-ops.
- If `[Unreleased]` had no `-` bullets (genuinely empty), the new version
  section still gets a placeholder line so it isn't a bare heading.

After this phase, the default invocation **pauses** (return 0) with the
message:

```
=== PAUSE: CHANGELOG cut done ===
Review and polish CHANGELOG.md as needed, then re-run with --resume to continue.
```

`--resume` skips the pause. `--dry-run` skips the pause and doesn't write.

## Phase 3: Commit + tag + push

- Subject: `chore(release): v<version>`. Skipped if HEAD subject already
  matches.
- Stages: `CHANGELOG.md`, `pyproject.toml` (the latter in case the operator
  bumped it just-in-time before invoking). Commit only if anything is
  actually staged.
- Annotated tag: `v<version>` with message `Explorer release <version>`.
  Skipped if the tag exists locally.
- Push: `git push origin <branch> --follow-tags`. Naturally idempotent —
  GitHub no-ops "already up-to-date" pushes.

The tag is pushed *now* (not after the build), but unlike KG's flow there's
no clean-clone-of-the-tag in Phase 4 — the build is deterministic from
`pyproject.toml` + the tree, so we just build the current tree, which is
the tag's tree.

## Phase 4: Build + verify

Two-step:

### 4a — Build

- `rm -rf dist/` (clean slate).
- `uv build` produces `dist/multiomics_explorer-<pep440-version>-py3-none-any.whl`
  and `dist/multiomics_explorer-<pep440-version>.tar.gz`.

PEP 440 normalizes pre-release suffixes:

| Tag | PEP 440 / wheel name |
|---|---|
| `v0.1.0-alpha.1` | `0.1.0a1` |
| `v0.1.0-beta.2`  | `0.1.0b2` |
| `v0.1.0-rc.1`    | `0.1.0rc1` |
| `v0.1.0`         | `0.1.0` |

The git tag stays in `-alpha.N` shape (so it stays readable + matches the
KG); only the wheel filename gets PEP-440'd. The script tracks both.

### 4b — Verify

Wheel-content checks (the spec §10 acceptance gates):

- **No leakage.** None of these prefixes appear in any wheel entry:
  `multiomics_explorer/inputs/`, `multiomics_explorer/cli/`, `tests/`,
  `.env`, `.venv/`.
- **LICENSE present.** Some entry contains the string `LICENSE`.
- **Throwaway venv install + import.** A fresh `uv venv` at
  `/tmp/explorer-release-check-<version>`, install the wheel into it,
  run `python -c "import multiomics_explorer"`. Must exit 0.
- **Console script registered.** `<venv>/bin/multiomics-kg-mcp` exists.

Cleans up the throwaway venv at the end.

## Phase 5: Publish

- **`dist/metadata.json`** — written next to the artifacts. Shape:

```json
{
  "version": "0.1.0-alpha.1",
  "tag": "v0.1.0-alpha.1",
  "git_sha": "...",
  "git_sha_short": "...",
  "git_branch": "main",
  "git_dirty": false,
  "python_requires": ">=3.11",
  "wheel": "multiomics_explorer-0.1.0a1-py3-none-any.whl",
  "sdist": "multiomics_explorer-0.1.0a1.tar.gz",
  "stamped_at": "<utc iso now>"
}
```

Mirrors KG's `metadata.json` shape, minus the graph-count keys (those don't
apply to a package). This is the authoritative artifact manifest;
CHANGELOG holds the human-readable prose.

- **Release-notes fragment** — `.release-notes-<version>.md` at repo root,
  extracted from the CHANGELOG `[<version>]` section. Cleaned up at end.

- **GitHub Release** — `gh release create v<version> --title "Explorer
  <version>" --notes-file <fragment>` with auto-applied `--prerelease`
  for any `X.Y.Z-<suffix>.N` version (i.e. any version with a `-`).
  `--draft` adds `--draft`. Wheel + sdist + `metadata.json` attached as
  release assets, so `uv add git+https://github.com/wosnat/multiomics_explorer.git@v<version>`
  works without a build dependency on the consumer side.

- **Operator announcement** — printed at the end:
  - The release URL.
  - The `uv add git+...@<tag>` install one-liner.
  - **KG-side coordination reminder.** The cross-repo contract is the KG's
    `Schema_info.mcp_min_version`. If the KG side is at a min-version
    greater than `<version>`, alpha testers will hit a compatibility
    warning at runtime. Coordinate with the KG release per KG plan §2.3
    when explorer + KG move together.

## Tester announcement template (manual; not auto-sent)

```
multiomics_explorer release v<version> is live.

- Release notes + artifacts: https://github.com/wosnat/multiomics_explorer/releases/tag/v<version>
- Install:  uv add git+https://github.com/wosnat/multiomics_explorer.git@v<version>
- KG compat: works against KG ≥ kg-<min-kg-version>. Run the KG
  compatibility check (see kg_mcp_guide §5) before driving the MCP.
- File issues at https://github.com/wosnat/multiomics_explorer/issues
  with the version tag in the title.
```

## Common operator flows

```bash
# Sanity-check the pipeline (dry-run, mutates nothing)
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1 --dry-run

# Real cut — pauses after CHANGELOG cut
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1
# ... review CHANGELOG.md, edit if needed ...
# Resume after polish
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1 --resume

# Release as a draft (don't publish publicly yet)
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1 --draft

# Release with a dirty working tree (rare, e.g. emergency hotfix)
uv run python .claude/skills/release-explorer/release_explorer.py 0.1.0-alpha.1 --allow-dirty
```

## When PyPI lands (future Phase 6)

Today, `Phase 5: Publish` ends at the GitHub Release. When PyPI is in
scope (per spec §11 row 2, currently deferred), a Phase 6 lands:

- Use Trusted Publishing via GitHub OIDC, NOT a long-lived API token in
  the script's env.
- `uv publish` (or `twine upload`) runs from a GitHub Actions workflow
  triggered by the tag push, not from this script. The script's
  responsibility ends at "tagged + Released on GitHub"; CI takes it from
  there.
- Skill SKILL.md gets a `--no-pypi` flag if local-only testing is wanted.
