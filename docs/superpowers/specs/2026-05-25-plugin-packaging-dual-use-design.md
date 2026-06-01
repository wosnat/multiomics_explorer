# Design: dual-use distribution — Python package + Claude Code plugin

**Date:** 2026-05-25
**Status:** **Superseded** by [2026-06-01-explorer-package-release-design.md](2026-06-01-explorer-package-release-design.md) — the plugin direction is dropped. Kept as record of why (per-user friction of `--plugin-dir`, no env-var alternative, VSCode-extension gap, redundancy with the research repo's plugin packaging).

## 1. Overview & goal

Make `multiomics_explorer` consumable by end users three ways from a single
clone, with minimal per-user configuration:

1. **As a Claude Code plugin** — `claude --plugin-dir <clone>` registers the
   MCP server (path auto-resolved) and loads two bundled skills.
2. **As an MCP server wired by hand** — documented escape hatch for users who
   don't want the plugin.
3. **As a Python package** — `import multiomics_explorer` after `uv sync`, for
   scripting and analysis.

The work is entirely additive and reversible: nothing here changes runtime
query logic, and dropping the plugin layer leaves the package + manual-MCP
paths fully functional.

## 2. Scope

**In scope:** files in *this* repo (`multiomics_explorer`) only.

**Out of scope (noted in §10):** the `multiomics_research` repo, a published
marketplace, PyPI publishing, a `userConfig` keychain credential prompt, and
support for non-Claude-Code agent tools (e.g. Antigravity).

## 3. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Ship a plugin? | Yes — add `.claude-plugin/plugin.json` | Lowest per-user friction; auto-resolves clone path; turns guide into an installable skill. GA + low lock-in (§9, §11). |
| Bundled skills | `experiment-characterization` + `multiomics-kg-guide` | Both user-facing. |
| Guide skill | Author a thin `SKILL.md` routing to existing `references/` + `docs://` resources | Makes the guide discoverable/invokable without duplicating content; generator keeps owning `references/`. |
| Credentials | `${NEO4J_*}` env-var passthrough (user-defined, outside the install) | Nothing edited inside the clone; `git pull` / reinstall never touches creds. |
| MCP path | `${CLAUDE_PLUGIN_ROOT}` (Claude Code injects it automatically, per-plugin) | No user-maintained path. |
| Distribution | Local `--plugin-dir` from clone | Matches the fork/clone flow; no marketplace. |

## 4. Component A — Plugin manifest

New file **`.claude-plugin/plugin.json`** (only this file lives in
`.claude-plugin/`):

```json
{
  "name": "multiomics-explorer",
  "description": "MCP server + research skills for a Prochlorococcus/Alteromonas multi-omics knowledge graph (Neo4j).",
  "version": "0.1.0",
  "author": { "name": "Osnat Weissberg" },
  "repository": "https://github.com/wosnat/multiomics_explorer",
  "keywords": ["multi-omics", "prochlorococcus", "knowledge-graph", "neo4j", "bioinformatics"]
}
```

The `skills` field points at the **existing** skills directory so no files
move and `build_about_content.py` keeps owning
`multiomics-kg-guide/references/`:

```json
  "skills": "./multiomics_explorer/skills/"
```

That directory contains exactly two subdirs (`multiomics-kg-guide`,
`experiment-characterization`), so only those two load, namespaced as
`multiomics-explorer:multiomics-kg-guide` and
`multiomics-explorer:experiment-characterization`.

## 5. Component B — MCP registration

The plugin's MCP server definition is declared **inline in `plugin.json`** (not
a separate plugin-root `.mcp.json`), so it stays plugin-scoped and cannot
pollute project-MCP reading. It uses `${CLAUDE_PLUGIN_ROOT}` to resolve to
wherever the user cloned, and passes credentials through from the user's
environment (§6):

```json
{
  "mcpServers": {
    "multiomics-kg": {
      "command": "uv",
      "args": ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}", "multiomics-kg-mcp"],
      "env": {
        "NEO4J_URI": "${NEO4J_URI}",
        "NEO4J_USER": "${NEO4J_USER}",
        "NEO4J_PASSWORD": "${NEO4J_PASSWORD}"
      }
    }
  }
}
```

This replaces today's `${MULTIOMICS_EXPLORER_DIR}` mechanism in the root
[.mcp.json](../../../.mcp.json) — but two committed registrations must be
addressed at the same time, or in-repo dev will triple-register
`multiomics-kg`:

- **`.mcp.json`** (project-MCP, committed) — delete. The plugin replaces it.
  Dev-in-repo with `claude --plugin-dir .` then gets exactly one registration
  (the plugin's).
- **`.claude/settings.json` top-level `mcpServers` block** (committed; hardcodes
  `/home/osnat/github/multiomics_explorer`, which does not exist on any other
  machine — and does not even match this machine's actual clone) — delete the
  `mcpServers` block. Keep `permissions`, `enabledPlugins`, `env`. This is
  author-specific config that was wrong-for-everyone-else from the start; the
  plugin makes it obsolete.

Confirm exact field semantics for inline `mcpServers` against the installed
Claude Code version (v2.1.150-era docs) before writing files.

## 6. Component C — Credentials

`config/settings.py` (pydantic-settings) reads from **OS environment variables
and** an `.env` file, with **env vars taking priority**. Field names map
case-insensitively to `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`.

The plugin's MCP `env` block (§5) passes these through from the user's own
environment. The user sets `NEO4J_*` once in their shell profile or their own
`~/.claude/settings.json` `env` block — **outside the install**. For the Python
package path this is automatic: `import multiomics_explorer` in the user's own
project reads *their* cwd's `.env` or env vars.

**The in-clone `.env` problem.** `env_file=".env"` in
[settings.py](../../../multiomics_explorer/config/settings.py) is a
**CWD-relative** path. The plugin launches via `uv run --directory
${CLAUDE_PLUGIN_ROOT} multiomics-kg-mcp`, so CWD becomes the clone root and
pydantic reads **the clone's own `.env`** if one exists. Today
[.env.example](../../../.env.example) prompts every new user to `cp
.env.example .env` (per [README](../../../README.md)), so an in-clone `.env` is
the *expected* state, not an edge case. This makes the §3 "nothing edited
inside the clone" rationale aspirational rather than current. Required
follow-through is in §8: remove the `cp .env.example .env` Quick Start step,
and trim `.env.example` to the `NEO4J_*` block.

**Caveat to verify (§12.2):** confirm how the installed Claude Code expands an
**unset** `${NEO4J_URI}`. If it injects an empty string into the process env,
it would override (and blank out) the in-clone `.env` fallback — concretely,
working creds in a developer's `.env` could be silently blanked by an empty
passthrough. Treat env-var passthrough and `.env` as **either/or**, not a
silent hybrid, until this is confirmed.

## 7. Component D — Thin `multiomics-kg-guide` SKILL.md

New file **`multiomics_explorer/skills/multiomics-kg-guide/SKILL.md`** (a few
dozen lines). It turns the existing doc tree into a discoverable skill by
*routing* to what already exists rather than duplicating it: the
`references/{guide,tools,analysis}/` files on disk and the `docs://...` MCP
resources. Frontmatter: `name: multiomics-kg-guide` plus a `description` /
`trigger` aimed at "how do I query this KG / which tool do I use."

`build_about_content.py` only writes `references/`, so regeneration will not
clobber the new `SKILL.md`. (Confirm the generator does not delete-then-rewrite
the whole skill dir — §12.3.)

## 8. Component E — Documentation

Targeted updates, not a full rewrite. Some of these are forced by §6 — the
credentials rewrite collides with content that would otherwise be left alone:

- **README.md** — replace the Quick Start / MCP section with three clearly
  separated install paths (plugin via `--plugin-dir`; manual MCP wiring with an
  explicit `uv run --directory <your-clone>` snippet; Python package usage),
  plus the `NEO4J_*` env-var creds step. Fix the stale `git clone <repo-url>`
  and hardcoded `/path/to/multiomics_explorer`. Add a one-line warning: do not
  enable this plugin *and* the `multiomics_research` plugin simultaneously —
  both register an MCP server named `multiomics-kg` (MCP server names are not
  namespaced across plugins). **Also fix, because §6 makes them actively
  misleading:** line 3 "a LangChain agent for natural language queries"
  (description), line 10 "API key for your LLM provider" prerequisite, lines
  18–19 `cp .env.example .env` / "Edit .env with your API key" Quick Start
  step, lines 95–99 `query` / `interactive` NL CLI commands. None of the three
  documented install paths needs an LLM API key; keeping that framing
  contradicts §6's env-var-only creds model.
- **`.env.example`** — trim to the `NEO4J_*` block (per §6). Drop `MODEL`,
  `MODEL_PROVIDER`, `MODEL_TEMPERATURE`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`.
  Keep the commented `KG_REPO_PATH` line.
- **CLAUDE.md** — update the "Claude Code Configuration" block (currently shows
  a `/home/osnat/...` path) to describe the plugin path as primary.

Leave unrelated staleness (LangChain-agent mentions in other files, tool
counts) untouched unless it actively misleads a new installer.

## 9. Verification & acceptance — clean-room isolation test

The headline acceptance requirement: prove the MCP server and skills are
provided **by the plugin**, not by pre-existing machine-level / home-directory
config. (This repo's dev machine already registers `multiomics-kg` via
`~/.claude` and the repo's own `.claude/`, so a naive "does it work" check
would pass spuriously.)

**Protocol:**

1. **Fresh plugin source:** clone `multiomics_explorer` to a new directory;
   run `uv sync` there so `uv run multiomics-kg-mcp` resolves dependencies.
2. **Clean working dir:** create a separate empty directory (the "new clean
   repo") with no `.claude/`, no `.mcp.json`, no inherited project config.
3. **Isolated user config:** launch Claude Code with user/home config isolated
   from the real one (e.g. a throwaway `CLAUDE_CONFIG_DIR`, or an equivalent
   isolation mechanism — exact method confirmed in planning, §12.4) so
   `~/.claude/settings.json` and `~/.claude.json` cannot leak in.
4. **Set creds** (`NEO4J_*`) in that shell only.
5. **Negative control (key step):** start a clean session in the working dir
   **without** the plugin. Assert the `multiomics-kg` MCP tools are **absent**
   and the two skills are **not** present. This proves the clean state is
   genuinely clean.
6. **Positive test:** start a clean session **with** the plugin enabled
   (`--plugin-dir <clone>`). Assert:
   - the `multiomics-kg` MCP server is listed and a representative tool call
     (e.g. `kg_schema`) returns successfully against Neo4j;
   - both skills are discoverable, namespaced as `multiomics-explorer:*`;
   - the guide skill resolves its `references/` content.
7. **Package path:** in the clean working dir, confirm `import multiomics_explorer`
   + a simple API call works using `NEO4J_*` from the environment (no `.env`
   inside the install).

**Regression checks:** re-running `build_about_content.py` leaves the new
`SKILL.md` intact; `pytest tests/unit/` stays green; `claude plugin validate`
(or equivalent) passes on the manifest.

## 10. Out of scope / future options

- Published marketplace (`marketplace.json`) for `/plugin install` without a
  manual clone.
- PyPI publishing (`pip install multiomics-explorer`).
- `userConfig` keychain prompt for the Neo4j password on plugin enable.
- A docs note / fix in `multiomics_research` for the `multiomics-kg` MCP name
  collision (other repo — out of scope here).
- Support for non-Claude-Code agent tools.

## 11. Portability / lock-in

The design concentrates value in **tool-agnostic** layers and keeps the
Claude-Code-specific surface thin and swappable:

- **Portable (zero rework if switching tools):** the Neo4j KG; the Python
  package; the MCP server (`multiomics-kg-mcp`); the `docs://` MCP resources;
  `NEO4J_*` env-var creds; all skill *content* (plain markdown).
- **Claude-Code-specific (the thin shell):** `.claude-plugin/plugin.json`,
  `${CLAUDE_PLUGIN_ROOT}` substitution, and the `SKILL.md` wrappers.

Migration to another MCP-capable agent tool is therefore a config swap plus
re-wrapping skill content into that tool's mechanism — roughly a day, no logic
rewrite — *provided the target tool supports MCP* (the cross-vendor standard).
The Claude Code plugin system is GA as of the v2.1.150 changelog (May 2026) with
no documented breaking changes to the interfaces used here, so near-term churn
risk is low; budget a brief compatibility check every few minor releases.

## 12. Open items to resolve during planning

1. **Root `.mcp.json` vs inline `mcpServers`** (§5): pick the approach that
   avoids project-MCP breakage and avoids double-registering `multiomics-kg`
   for in-repo dev. Confirm field semantics against the installed version.
2. **Unset-`${VAR}` expansion** (§6): confirm whether an unset `${NEO4J_*}`
   becomes an empty string that overrides `.env`.
3. ~~**Generator safety** (§7)~~ — **RESOLVED.** Verified
   [build_about_content.py](../../../scripts/build_about_content.py) only ever
   does `output_path.write_text()` on individual `references/tools/{tool}.md`
   files (with `mkdir(parents=True, exist_ok=True)`); it never deletes, and
   `OUTPUT_DIR` is the `references/tools/` subdir. The proposed `SKILL.md`
   lives at the skill root, two levels above — never touched by the generator.
   Safe.
4. **Config-isolation mechanism** (§9.3): confirm the exact way to run Claude
   Code with isolated user/home config for the clean-room test
   (`CLAUDE_CONFIG_DIR` or equivalent).
