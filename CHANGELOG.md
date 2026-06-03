# Changelog

All notable changes to `multiomics_explorer` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow the scheme `X.Y.Z[-(alpha|beta|rc).N]` (mirrors the KG repo)
and are tagged `vX.Y.Z…`.

**Process (accumulate-then-cut):** log notable changes under `[Unreleased]` as
they land. At release time, `/release-explorer` *cuts* `[Unreleased]` into a
dated version section, stamps the same version onto `pyproject.toml`, and
renders the GitHub Release notes from that section. The changelog is the
source of truth; the GitHub Release is a rendering of one section. See
`.claude/skills/release-explorer/SKILL.md`.

**Cross-repo contract:** the KG declares its minimum-compatible explorer
version via `Schema_info.mcp_min_version`. When a release here changes the
contract (new MCP tools, breaking arg shape, return-shape changes), bump
the version accordingly and coordinate with the KG-side `mcp_min_version`
ahead of the KG release. See KG plan §2.3 for the coordination dance.

## [Unreleased]

### Added
- `kg_release_info` MCP tool: returns the KG's release identity
  (`Schema_info` properties — version, built_at, counts, git identity)
  and a three-valued compatibility verdict (`ok` / `warn` / `unknown`)
  against the installed explorer version. Run by the MCP server lifespan
  at startup; cached on `KGContext`; tool reads from cache. PEP 440
  version comparison via `packaging.version.Version` (catches the
  pre-release-vs-release coordination case). 16 asserts in the v1
  EXPECTED_KG_SHAPE check (5 Schema_info properties + 5 node labels +
  3 relationship types + 2 non-zero counts + 1 version compat). See
  `docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md`.
- MCP server `instructions` updated to point agents at `kg_release_info`
  as a first call in any new session.
- Read-only Python toolkit for the Prochlorococcus/Alteromonas multi-omics
  knowledge graph (Neo4j). Two surfaces shipped:
  - **Python API** (`multiomics_explorer.api.functions`) — programmatic
    access for scripting and notebook use.
  - **MCP server** (`multiomics-kg-mcp`) — ~39 domain-specific tools for
    Claude Code: gene resolution, expression lookups, ontology enrichment,
    metabolite searches, derived-metric drill-downs, clustering, sequence /
    neighborhood lookup, ortholog navigation, and a `run_cypher` escape
    hatch (writes blocked).
- Neo4j env-var hygiene: `NEO4J_USERNAME` canonical (matches Neo4j BKM —
  Aura "Connect" credential file, Cypher Shell), `NEO4J_USER` accepted as
  back-compat alias via pydantic `AliasChoices`. `NEO4J_DATABASE` plumbed
  through to `driver.session(database=...)` (default `"neo4j"`).
- PyPI-readiness metadata in `pyproject.toml`: `[project.urls]`, keywords,
  classifiers, License-File. Wheel build excludes dev-only `inputs/`
  (consumed by `scripts/build_about_content.py`); LICENSE + generated
  skills/MD ship.
- `CHANGELOG.md` (this file) and the `/release-explorer` skill (`.claude/skills/release-explorer/`).

### Changed
- Tag scheme finalized as `v<version>` matching the KG's pre-release suffix
  discipline (`-(alpha|beta|rc).N`). First release is `v0.1.0-alpha.1`,
  not bare `v0.1.0`, to support the alpha cycle cleanly.

### Removed
- The `multiomics-explorer` CLI surface (only `multiomics-kg-mcp` console
  script remains). `typer` and `rich` dropped from runtime dependencies.
- Unused LangChain-agent fields from `Settings` (`model`, `model_provider`,
  `model_temperature`, `anthropic_api_key`, `openai_api_key`).
- Committed `mcpServers` block in `.claude/settings.json` (was hardcoded to
  one machine's path); simplified `.mcp.json` to drop the
  `${MULTIOMICS_EXPLORER_DIR}` indirection.

### Fixed
- `NEO4J_DATABASE` was previously a silent no-op (env var was documented in
  the KG MCP guide but ignored by the explorer). Driver session now honors
  it; forward-compatible for future non-default-DB releases.
