# Design: explorer as a releasable Python package

**Date:** 2026-06-01
**Status:** Approved — all open items resolved 2026-06-01.
**Supersedes:** [2026-05-25-plugin-packaging-dual-use-design.md](2026-05-25-plugin-packaging-dual-use-design.md) — the plugin direction is dropped; this spec replaces it.
**Related:** `multiomics_biocypher_kg/plans/alpha_release.md` (the consumer; the KG alpha plan §2.7 assumes a clean explorer install delivered transitively via `multiomics_research`).

## 1. Overview & goal

Make `multiomics_explorer` a clean, releasable Python package consumable two ways:

1. **Primary path — as a transitive dependency of `multiomics_research`.** Alpha testers fork `multiomics_research`, `uv sync`, and the explorer (library + MCP server + CLI) comes in via that fork's `pyproject.toml`. The research repo also owns Claude Code wiring (plugin manifest + MCP registration). Per KG alpha plan §2.7.
2. **Standalone — direct `uv add`.** Users who want the library or MCP server in their own Python project without going through `multiomics_research` install it directly.

README is **user-facing**, with a short **Development** section at the bottom for contributors working on the explorer itself.

No plugin layer here (the research repo owns that). No skill handling here (skills live in `multiomics_research`).

## 2. Scope

**In scope:**
- `pyproject.toml` hygiene for release.
- Settings cleanup: prune dead LangChain-agent fields.
- Credentials model: env vars only for the install model; `.env` supported for dev convenience only.
- Version contract: package version IS the value `Schema_info.mcp_min_version` compares against (KG plan §2.1).
- Repo cleanup: drop the committed `mcpServers` block in `.claude/settings.json`; simplify the committed `.mcp.json`.
- README: user-facing structure with optional Development section.
- `.env.example` trim.
- Acceptance: clean `uv build`, fresh-venv install round-trip, tests pass.

**Out of scope:**
- Plugin manifest / `.claude-plugin/` (the research repo handles plugin packaging — see [superseded spec](2026-05-25-plugin-packaging-dual-use-design.md) for the rejected approach).
- Skill handling (`multiomics-kg-guide`, `experiment-characterization`) — owned by `multiomics_research`.
- A new MCP compatibility-check tool that reads `Schema_info.mcp_min_version` and compares to the installed explorer version — separate feature work. This spec only ensures the package version *exists* to satisfy the contract; the tool that uses it is its own brainstorm (suggested shape: a new MCP tool `kg_release_info` returning `Schema_info` properties + a comparison verdict).
- PyPI publishing — deferred. Git install is the v1 path; PyPI name-availability check + first release happen later (no blocker for the alpha).
- Neo4j hosting / connection-string distribution — KG alpha plan owns these.
- CLI surface — dropped entirely in this spec (see §3 locked decisions; no users today, no plans).

## 3. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Distribution model | `uv add` per project (transitively via `multiomics_research`, or directly) | Single source of truth per venv; no drift between MCP and library; reproducible via `uv.lock`. (Rejected: `uv tool install` — caused drift; plugin packaging — overkill, research repo owns it.) |
| Repo visibility | Public | Install URL uses HTTPS (`git+https://...`); no SSH-key prerequisite for Windows users. |
| Install source for v1 | `git+https://github.com/wosnat/multiomics_explorer.git` | Works today without a release; PyPI deferred (name check + first release happen later, no alpha blocker). |
| Credentials | `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` env vars only in the install model; `.env` supported for in-clone dev | Aligned with KG plan's "shared `explorer` login distributed out-of-band." `.env` is a dev convenience, not part of the user install. |
| Version semantics | Semver; `pyproject.toml` version IS the value satisfied against `Schema_info.mcp_min_version` | Establishes the explorer↔KG contract per KG plan §2.1, §6.4(5). |
| Initial version | `0.1.0` (matches live KG: `Schema_info.mcp_min_version="0.1.0"`, verified 2026-06-01 against the dev KG) | Verified contract; explorer at `0.1.0` satisfies the KG's declared minimum. |
| Tag prefix | `v0.1.0` | PyPI-familiar convention; one prefix shape, used for the eventual release script. |
| Release artifact | Git tag `v<version>` + a GitHub Release | Mirrors KG plan's release pattern; release script is a follow-up. |
| CLI surface | Removed entirely — delete `multiomics_explorer/cli/`, the `multiomics-explorer` console script, and the `typer`/`rich` runtime deps | No users today, no plans (confirmed 2026-06-01). MCP is the primary surface; the Python API covers scripting. Removing the CLI shrinks the install and drops two runtime deps. |
| README primary audience | End users (alpha testers) | Dev material moved to a clearly-marked Development section at the bottom. |
| Dev surface | `.mcp.json` at repo root, simplified | Contributors get a working MCP server pointing at their own checkout via `uv run multiomics-kg-mcp`. End users never see it. |
| MCP env block syntax | Literal `${VAR}` in `.mcp.json` (late-expanded by Claude Code at MCP launch), not pre-expanded `--env VAR=$VAR` | Verified 2026-06-01: Claude Code re-expands `${VAR}` from host env at launch; unset vars cause a parse failure (no silent empty-string passthrough). Late expansion lets the user set env vars in their shell *after* registration. |
| Neo4j auth env var names | `NEO4J_USERNAME` canonical (matches Neo4j BKM — Aura's "Connect" credential file, Cypher Shell, GraphAcademy); `NEO4J_USER` accepted as back-compat alias via `AliasChoices` | Anyone pasting credentials from Aura's UI Just Works; existing `.env` files keep working. Decided 2026-06-02 during review. |
| Neo4j database env var | `NEO4J_DATABASE` (default `"neo4j"`); plumbed through to `driver.session(database=...)` | Forward-compatible: today's KG uses the default `neo4j` DB so it's a no-op, but a future release on a non-default DB will not silently fail. Closes a silent-no-op surfaced in review (KG MCP guide already documents `NEO4J_DATABASE`, but the explorer was ignoring it). |

## 4. Package hygiene (pyproject.toml)

Current state: [pyproject.toml](../../../pyproject.toml) — already mostly clean (MIT license declared, hatchling build, console scripts wired). Changes needed:

- **Move `pytest>=9.0.2` out of `dependencies` into `[dependency-groups] dev`** ([pyproject.toml:25](../../../pyproject.toml#L25)). Currently a runtime dependency, so every `uv add multiomics-explorer` pulls pytest into the user's project. Wrong — pytest is for the explorer's own test suite, not its consumers.
- **Drop `typer>=0.12.0` and `rich>=13.0` from `dependencies`** ([pyproject.toml:22-23](../../../pyproject.toml#L22-L23)). Both are CLI-only (verified 2026-06-01: imported by `multiomics_explorer/cli/main.py` and `tests/integration/test_cli.py` only). With the CLI removed, no runtime consumer remains.
- **Drop the `multiomics-explorer` console script** from `[project.scripts]` ([pyproject.toml:45](../../../pyproject.toml#L45)). Only `multiomics-kg-mcp` remains.
- **Add PyPI-readiness metadata** (in preparation for a later PyPI release):
  - `[project.urls]` with `Repository`, `Issues` (optional: `Documentation`).
  - `keywords = ["multi-omics", "prochlorococcus", "knowledge-graph", "neo4j", "bioinformatics"]`.
  - `classifiers` — at minimum License (MIT), Programming Language :: Python :: 3.11, Topic :: Scientific/Engineering :: Bio-Informatics.
  - Confirm `license = {text = "MIT"}` resolves correctly with hatchling; if not, switch to `license-files = ["LICENSE"]` per PEP 639.

LICENSE file present ([LICENSE](../../../LICENSE), MIT, 1063 bytes). No new file needed.

Console script after the prune: only `multiomics-kg-mcp = "multiomics_explorer.mcp_server.server:main"`.

## 5. Code cleanup

Two prunes — dead LangChain-agent settings, and the now-removed CLI:

**Dead LangChain settings:**
- **[multiomics_explorer/config/settings.py:18-25](../../../multiomics_explorer/config/settings.py#L18-L25)** — delete fields `model`, `model_provider`, `model_temperature`, `anthropic_api_key`, `openai_api_key`. Remove the unused `Optional` import if no longer needed. `Settings` shrinks to Neo4j connection fields + the optional `kg_repo_path` dev knob.
- **[tests/unit/test_settings.py](../../../tests/unit/test_settings.py)** — three assertions reference the deleted fields (`s.model_temperature`, `s.model_provider`, `s.model` at lines 12, 36, 35). Delete those assertions and any test cases that exist solely to exercise them.

**CLI removal:**
- Delete the entire **[multiomics_explorer/cli/](../../../multiomics_explorer/cli/)** directory. Single module today ([cli/main.py](../../../multiomics_explorer/cli/main.py), 423 lines of typer commands).
- Delete **[tests/integration/test_cli.py](../../../tests/integration/test_cli.py)** (only consumer of `typer` in tests).
- Verify no remaining imports of `multiomics_explorer.cli.*` anywhere (`grep -rn 'multiomics_explorer\.cli'` should be empty after deletion).

**No other code/import prune needed.** Verified 2026-06-01: no `langchain` imports anywhere in [multiomics_explorer/](../../../multiomics_explorer/); no `agents/` directory. After the two prunes above, `typer` and `rich` have zero importers.

**Neo4j Settings shape (align with Neo4j BKM + fix silent-no-op on `NEO4J_DATABASE`):**
- **[multiomics_explorer/config/settings.py:15](../../../multiomics_explorer/config/settings.py#L15)** — rename field `neo4j_user` → `neo4j_username`; declare `AliasChoices("NEO4J_USERNAME", "NEO4J_USER")` so both env-var names resolve. `NEO4J_USERNAME` becomes canonical (Neo4j BKM); `NEO4J_USER` is back-compat.
- **[settings.py](../../../multiomics_explorer/config/settings.py)** — add `neo4j_database: str = "neo4j"`.
- **[multiomics_explorer/kg/connection.py:46](../../../multiomics_explorer/kg/connection.py#L46)** — change `self.driver.session()` to `self.driver.session(database=self._settings.neo4j_database)`.
- **[.env.example](../../../.env.example)** — rename `NEO4J_USER=` → `NEO4J_USERNAME=`; add a commented `# NEO4J_DATABASE=neo4j` (default).
- **Test sync:** update tests that construct `Settings(neo4j_user=...)` to `neo4j_username=...`.

Acceptance for this section: `pytest tests/unit/ -v` green after the prunes; `ruff check multiomics_explorer/` clean; `uv lock` shows `typer` and `rich` no longer in the resolved tree.

## 6. Credentials model

`config/settings.py` (pydantic-settings) reads from **OS environment variables** and an `.env` file, with **env vars taking priority** (pydantic-settings default precedence).

**User install model — env vars only:**
- Users set `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` (and optionally `NEO4J_DATABASE`, default `"neo4j"`) in their shell profile (bash/zsh) or Windows User Environment Variables (PowerShell). `NEO4J_USER` is accepted as a back-compat alias for `NEO4J_USERNAME`.
- For MCP registration, the env block in `.mcp.json` (or the equivalent in the research-repo template) passes them through to the spawned MCP process via literal `${VAR}` expansion (§3, §10 step 9).
- No `.env` file involved.

**Dev model — `.env` supported in the clone:**
- Contributors working on the explorer can put `.env` in the repo root; `env_file=".env"` ([settings.py:31](../../../multiomics_explorer/config/settings.py#L31)) is CWD-relative and the repo root is the CWD when running `uv run multiomics-kg-mcp` in-clone.
- Documented in the README's Development section, not the user-facing section.
- `.env` remains gitignored ([.gitignore:109](../../../.gitignore#L109)).

**`.env.example` trim** ([.env.example](../../../.env.example)):
- Keep + rename: `NEO4J_URI`, `NEO4J_USERNAME` (renamed from `NEO4J_USER` per §5), `NEO4J_PASSWORD`, and a new commented `# NEO4J_DATABASE=neo4j` (default). The commented `KG_REPO_PATH` line stays.
- Drop: `MODEL`, `MODEL_PROVIDER`, `MODEL_TEMPERATURE`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (their backing Settings fields go in §5).

**Env passthrough mechanics — verified 2026-06-01.** Claude Code supports `${VAR}` and `${VAR:-default}` syntax in `.mcp.json` `env` blocks; the substitution is late-bound (re-evaluated against the host environment at MCP launch time, not at registration time). If a referenced `${VAR}` is unset and no default is given, **Claude Code fails to parse the config** — it does *not* silently pass an empty string. So:

- **Use literal `${NEO4J_URI}` etc. in `.mcp.json`** (not shell-expanded `--env NEO4J_URI=$NEO4J_URI`). Late expansion lets the user set the env vars in their shell at any time, including after MCP registration.
- **`claude mcp add --env` flag**: behavior at the CLI level is undocumented; it may shell-expand at registration time. The safe approach is to register first, then **edit `.mcp.json` to use literal `${VAR}` syntax** — or hand-write the file from the start.
- **The dev-`.env` blanking-out concern is closed.** Since unset `${VAR}` fails-to-parse rather than passing empty, the in-clone `.env` is never silently overridden by an empty MCP env var.

## 7. Version contract

**The contract** (per KG plan §2.1, §6.4(5)): the KG stamps `Schema_info.mcp_min_version` at release time; the explorer's installed version is compared against it; mismatch = warn or abort.

**Live KG verified 2026-06-01** (`MATCH (s:Schema_info) RETURN s`): `Schema_info` node exists with `mcp_min_version="0.1.0"`, `version="0.0.0-dev"` (dev stamp), `built_at="2026-05-31T09:29:25.25Z"`, plus the count rollups (gene_count=120416, experiment_count=197, expression_edge_count=232758, organism_count=45, paper_count=43). The contract surface is in place ahead of the alpha release script.

**This spec ensures the package version exists and is meaningful:**

- **Semver discipline.** `pyproject.toml`'s `version` field is the source of truth; bump on any change that affects the explorer↔KG contract (new MCP tools, breaking arg changes, return-shape changes, etc.). Patch bumps for additive non-breaking changes.
- **Initial release version: `0.1.0`.** Satisfies the live KG's declared `Schema_info.mcp_min_version="0.1.0"`.
- **Tagging.** Git tag matches `pyproject.toml` version with prefix `v` — first release tag is `v0.1.0`.
- **Release script is NOT in this spec.** Mirrors the KG plan's `/release-kg` skill if/when needed — separate work item.

**The compatibility-check feature that uses this contract** (a new MCP tool that reads `Schema_info.mcp_min_version` from the KG and compares to the installed explorer version) is **out of scope** for this spec (§2). This spec only establishes the version-as-contract; the tool that exercises it is feature work.

## 8. Committed dev config cleanup

**Delete:**
- The `mcpServers` block in [.claude/settings.json:32-42](../../../.claude/settings.json#L32-L42). Hardcodes `/home/osnat/github/multiomics_explorer` — does not exist on any other machine, and does not even match the current clone path. Author-specific config that was wrong-for-everyone-else from the start. Keep `permissions`, `enabledPlugins`, `env`.

**Keep, simplified:**
- [.mcp.json](../../../.mcp.json) at repo root — becomes the dev-in-repo MCP registration. Simplify to:
  ```json
  {
    "mcpServers": {
      "multiomics-kg": {
        "command": "uv",
        "args": ["run", "multiomics-kg-mcp"]
      }
    }
  }
  ```
  Drops the `${MULTIOMICS_EXPLORER_DIR}` indirection (no longer needed — `uv run` from CWD picks up the project venv automatically when Claude Code launches from the clone). Documented in the Development section as "trust this on first prompt; it gives you a live MCP server against your in-tree code."

  This dev-in-repo form deliberately has **no env block** — it relies on `.env` in the repo root (§6 dev model). The user-facing form (literal `${VAR}` env block, no `.env`) is described in §6 user model and produced by the `multiomics_research` template, not by this file.

End users never see either file — their MCP registration comes from the research-repo template or `claude mcp add` in their own project.

## 9. README structure

**Audience split:** user-facing top (alpha testers + standalone consumers), Development section at the bottom (contributors). The Tool Tracker / LangChain-agent prose / "API key for your LLM provider" prerequisite all disappear.

Outline (the actual README is a follow-up implementation per this outline):

```
# multiomics-explorer

[One paragraph: read-only query toolkit for a Prochlorococcus/Alteromonas multi-omics
knowledge graph (Neo4j). Two surfaces: Python API and MCP server (for Claude Code).
Designed to be installed as a dependency, not cloned.]

## Install

### As a dependency of multiomics_research (recommended)
If you're using the multiomics_research analysis environment, the explorer is
installed automatically — see <link>.

### Standalone
For using the library or MCP server in your own Python project:

    uv add git+https://github.com/wosnat/multiomics_explorer.git

(PyPI release planned.)

## Prerequisites
- Python 3.11+
- uv:
    Linux/macOS:  curl -LsSf https://astral.sh/uv/install.sh | sh
    Windows:      winget install astral-sh.uv
- A running Neo4j KG instance — your administrator provides NEO4J_URI / USER / PASSWORD.

## Configure Neo4j credentials
bash/zsh (~/.bashrc, ~/.zshrc):
    export NEO4J_URI=neo4j+s://your-kg-host:7687
    export NEO4J_USERNAME=explorer
    export NEO4J_PASSWORD=...
    # Optional, defaults to "neo4j":
    # export NEO4J_DATABASE=neo4j
Windows (PowerShell):
    [Environment]::SetEnvironmentVariable("NEO4J_URI", "neo4j+s://...", "User")
    ...
(NEO4J_USER is accepted as a back-compat alias for NEO4J_USERNAME.)

## Use as a Python library
    from multiomics_explorer import gene_overview, GraphConnection
    with GraphConnection() as conn:
        result = gene_overview(["PMM_1234"], conn=conn)

## Use the MCP server with Claude Code
If you're not getting it through multiomics_research, register it in your project:
    claude mcp add multiomics-kg --scope project -- uv run multiomics-kg-mcp
Then edit `.mcp.json` to use literal `${NEO4J_URI}` etc. in the env block so
Claude Code re-expands them from your shell at launch time (the values are
not baked in at registration).

---

## Development

For contributors working on the explorer itself.

    git clone https://github.com/wosnat/multiomics_explorer.git
    cd multiomics_explorer
    uv sync

    pytest tests/unit/ -v          # no Neo4j needed
    pytest -m kg -v                # requires Neo4j at $NEO4J_URI

A `.mcp.json` at the repo root auto-registers an MCP server pointing at your
in-tree code when Claude Code is launched from the clone — your local edits
are picked up immediately. Trust the registration on first prompt.

`.env` in the repo root is supported as a dev-only convenience (CWD-relative).
For the install model, use env vars in your shell profile — `.env` is not
shipped with the install.
```

**Things to NOT carry over from the current README:**
- "a LangChain agent for natural language queries" framing.
- "API key for your LLM provider" prerequisite.
- `cp .env.example .env` Quick Start step.
- The entire CLI section (`stats` / `schema` / `cypher` / `query` / `interactive`) — CLI is removed in §3/§5.
- The full Tool Tracker (moves to docstrings / [CLAUDE.md](../../../CLAUDE.md) which already has the canonical list).

## 10. Verification & acceptance

1. **Build clean.** `uv build` produces wheel + sdist. Inspect the wheel: no `.env`, no `.venv`, no `inputs/`, no `tests/`, no `cli/` leakage; LICENSE included.
2. **Install round-trip in a fresh venv** (any directory, no clone):
   - `uv venv /tmp/explorer-test && cd /tmp/explorer-test`
   - `uv pip install <path-to-built-wheel>`
   - `.venv/bin/multiomics-kg-mcp --help` (or equivalent) succeeds.
   - **No `multiomics-explorer` console script** is installed (CLI is gone).
   - `.venv/bin/python -c "import multiomics_explorer; print(multiomics_explorer.gene_overview)"` succeeds.
3. **Dep tree shrunk.** `uv tree` (or equivalent) shows `typer`, `rich`, and `pytest` are absent from the runtime install (pytest stays in the dev group).
4. **Tests pass after the prunes.** `pytest tests/unit/ -v` green (with the settings-test cleanup); `pytest -m kg -v` green against a live Neo4j. No `tests/integration/test_cli.py` remaining.
5. **Lint clean.** `ruff check multiomics_explorer/` no worse than baseline.
6. **Repo cleanup applied.** `git diff` confirms the `mcpServers` block is gone from `.claude/settings.json`; `.mcp.json` is the simplified form; `multiomics_explorer/cli/` is deleted.
7. **README readability check.** A reader unfamiliar with the project can follow the user-facing section top-to-bottom and end up with: `uv add` succeeded, env vars set, MCP registered in their own project, and a Python-API example run successfully — without scrolling into the Development section.
8. **`uv add git+...` round-trip from a different machine** (or `/tmp` checkout): create an empty project, `uv add git+https://github.com/wosnat/multiomics_explorer.git`, confirm the same import + MCP-binary works. Proves the install path the README promises actually works.
9. **MCP env passthrough.** Register the MCP with literal `${NEO4J_URI}` in `.mcp.json`; confirm Claude Code launches the server with the host-shell value (late expansion). Confirm that an unset `${NEO4J_URI}` produces a parse-time error rather than a silent empty-string passthrough (verified behavior — §6).
10. **Env var alias resolution.** Set only `NEO4J_USERNAME` in the shell, start the MCP, confirm auth succeeds. Then set only `NEO4J_USER` (no `NEO4J_USERNAME`), restart, confirm auth still succeeds. Both should round-trip via the `AliasChoices` added in §5.
11. **Database passthrough.** With `NEO4J_DATABASE` unset, confirm the driver session uses the default `neo4j` database (today's KG). Set `NEO4J_DATABASE=neo4j` explicitly, confirm same result. The non-default-DB path will be exercised when a future KG release ships on one; this step proves the wire is live.

## 11. Resolution log

All six items from the draft are closed; nothing blocks implementation. Recorded here so the rationale is preserved alongside the spec.

| # | Item | Resolution (2026-06-01) | Lands in |
|---|---|---|---|
| 1 | Repo visibility | **Public.** Install URL is `git+https://github.com/wosnat/multiomics_explorer.git`. No SSH-key prerequisite. | §3, §9 README outline |
| 2 | PyPI name availability | **Deferred.** Git install is v1; PyPI name check + first PyPI release happen later. No blocker for the alpha. | §2 out-of-scope, §3 |
| 3 | Tag prefix | **`v0.1.0`.** PyPI-familiar; single shape. | §3, §7 |
| 4 | `Schema_info.mcp_min_version` check tool | **Out of scope.** Separate feature work; suggested shape noted in §2. Contract verified live on the dev KG 2026-06-01 (`Schema_info.mcp_min_version="0.1.0"`). | §2 out-of-scope, §7 |
| 5 | CLI scope | **Dropped entirely.** No users today, no plans. CLI directory deleted, `typer`/`rich`/`pytest` removed from runtime deps, `multiomics-explorer` console script removed. | §3, §4, §5, §9, §10 |
| 6 | Unset-`${VAR}` empty-string passthrough | **Verified.** Claude Code supports `${VAR}`/`${VAR:-default}` late expansion in `.mcp.json`; unset vars with no default cause a parse failure (no silent empty-string). Recommended: literal `${VAR}` in `.mcp.json`, not pre-expanded `--env`. | §3, §6, §9 README outline, §10 acceptance step 9 |
| 7 | Neo4j auth env var names (review, 2026-06-02) | **`NEO4J_USERNAME` canonical (Neo4j BKM); `NEO4J_USER` back-compat alias** via `AliasChoices`. Settings field renamed `neo4j_user` → `neo4j_username`. Aura's "Connect" credential file pastes cleanly; existing `.env` files keep working. | §3, §5, §6, §10 acceptance step 10 |
| 8 | `NEO4J_DATABASE` plumbing (review, 2026-06-02) | **Add `neo4j_database: str = "neo4j"` to Settings; plumb to `driver.session(database=...)`.** Today's KG uses the default `neo4j` DB (no-op); forward-compatible for future non-default-DB releases. Closes a silent-no-op surfaced during review (KG MCP guide already documents `NEO4J_DATABASE`, but the explorer was ignoring it). | §3, §5, §6, §10 acceptance step 11 |

## 12. Verification log

Evidence gathered while closing the open items, kept for future-self / reviewer auditability.

- **Live KG state** (2026-06-01, query `MATCH (s:Schema_info) RETURN s`): `version="0.0.0-dev"`, `mcp_min_version="0.1.0"`, `built_at="2026-05-31T09:29:25.25Z"`, `git_sha="unknown"` (dev stamp). Counts: gene 120416, experiment 197, expression-edge 232758, organism 45, paper 43. → confirms contract surface is in place and explorer `0.1.0` satisfies it.
- **Code audit** (2026-06-01, `grep` over the package): no `langchain` imports; no `agents/` directory; the deleted settings fields (`model`, `model_provider`, `model_temperature`, `anthropic_api_key`, `openai_api_key`) are referenced only by `tests/unit/test_settings.py` (3 assertions). `typer` and `rich` imported only by `multiomics_explorer/cli/main.py` and `tests/integration/test_cli.py`. → prunes are safe.
- **Claude Code MCP env passthrough** (researched against official docs, 2026-06-01): `${VAR}` and `${VAR:-default}` syntax supported in `.mcp.json` `env` blocks; substitution is late-bound at MCP launch; unset `${VAR}` without default → parse failure (no silent empty-string passthrough). `claude mcp add --env` CLI-level expansion semantics are undocumented; recommend hand-editing `.mcp.json` post-registration to use literal `${VAR}`.
