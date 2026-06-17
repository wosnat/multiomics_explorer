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

### Changed

### Fixed

## [0.1.0-alpha.4] - 2026-06-17
### Fixed
- `to_dataframe()` no longer drops the polymorphic `value` column from
  `gene_derived_metrics` results when a query mixes metric kinds (e.g. numeric
  + boolean + categorical). Such columns hold mixed scalar Python types, which
  pandas types as `object`; the flattener previously treated any non-list/dict
  `object` column as unflattenable and dropped it with a warning. Mixed-scalar
  columns are now kept as-is. Columns with genuine nesting still drop as before.

## [0.1.0-alpha.3] - 2026-06-15
### Added
- Corner-case verification harness (`tests/integration/edge_cases/` +
  `tests/integration/test_edge_case_contracts.py`): every MCP tool is exercised
  against degenerate-but-valid inputs (genome-only / expression-empty
  organisms, missing & mixed batches, pagination/filter-empty boundaries,
  null-valued properties such as coordinate-less genes) and
  checked against structural invariants (no crash, schema validity, count
  consistency, batch-diagnostic subsetting, empty-layer shape). A self-validating
  fixture bank re-pins after KG rebuilds, and a coverage gate fails if a
  registered tool has no edge-case scenarios.

### Changed

### Fixed
- `differential_expression_by_gene` no longer crashes on genes with zero
  differential-expression edges. The batch `top_categories` builder leaked a
  synthetic `{category: null, …}` row that violated the non-nullable
  `ExpressionTopCategory.category` model (raising a `ToolError`); null
  categories are now filtered out in both the batch and global builders.
  Surfaced by the new corner-case harness.
- Organism resolution no longer requires expression data. The shared
  `_validate_organism_inputs` resolver matched `Experiment` nodes with
  `gene_count > 0`, so genome-only (`experiment_count=0`) and
  metabolomics-only strains were unresolvable — every single-organism
  genomic tool (`genes_by_ontology`, `gene_ontology_terms`, …) raised
  `no organism matching '<name>' found` for them. Now matches
  `OrganismTaxon` with `gene_count > 0` (genomic presence, not expression),
  so any real organism — including genome-only / metabolomics-only strains —
  resolves, while gene-less higher-rank taxonomy nodes (genus / phage /
  non-target species) still raise a clear not-found instead of silently
  returning empty results.

## [0.1.0-alpha.2] - 2026-06-13
### Added
- `discussed_by_publication` MCP tool — forward literature-index lookup
  (publication DOIs → genes + KEGG pathways the paper names in prose).
  `UNION ALL` over `Publication_discusses_gene` +
  `Publication_discusses_kegg_pathway`; polymorphic rows
  (`entity_kind` / `entity_id` / `entity_name` / `prominence`, union-padded
  organism), summary rollups (`by_entity_kind`, `by_prominence`,
  `top_kegg_pathways`, `top_publications`), case-insensitive DOI matching,
  `not_found` / `not_matched`, offset pagination. Recall-biased narrative
  router — NOT exhaustive, NOT DE-table expression.
- Discusses literature-index surfaced across 3 existing discovery tools:
  `gene_overview` (per-gene `discussed_in_publication_count`, envelope
  `has_discussed` + `top_discussing_publications`; verbose
  `discussed_in_publications`), `list_publications` (per-row
  `discussed_gene_count` / `discussed_pathway_count`, envelope
  `by_discusses_coverage`), `search_ontology` (KEGG-only
  `discussed_by_n_publications`; verbose per-term `discussed_in_publications`).
- `kg_release_info` surfaces `Schema_info.release_highlights` +
  `breaking_changes` — passthrough of two optional properties the KG stamps
  on official (non-dev) releases. `KGIdentity` gains both fields (`str | None`,
  `None` on dev/legacy builds); `summary` appends short pointers when present.
  Kept passive by design (no recurring `ctx.warning`).
- `kg_release_info` surfaces `Schema_info.deployment_role`
  (`local-dev` | `staging` | `production`), stamped by the KG at build time.
  Flows through `_KG_IDENTITY_FIELDS` + `KGIdentity` like other identity
  fields; `null` → rendered as unknown on legacy KGs.

### Changed
- Correctness pass on the LLM-facing doc surface (guides, analysis docs, tool
  YAMLs, `CLAUDE.md`, server instructions) reconciled with the current
  41-tool set and live KG: tool count normalized to 41, stale `query=` alias
  removed from 5 example calls, missing `kg_release_info` row + summary stats
  added, enrichment/metabolites/concepts/conventions doc fixes.
- Anti-drift guards added (`tests/unit/test_about_content.py`): validate every
  example/steps/chaining kwarg against the live tool schema; assert every
  registered tool has a YAML + doc + `CLAUDE.md` row; assert hard-coded
  "N tools" claims match the live registry. Removed the stale
  experiment-characterization skill.

### Fixed
- `discussed_by_publication`: rename APOC frequency keys
  (`by_entity_kind` / `by_prominence`) to the semantic keys the Pydantic
  breakdown models require — a mock-invisible Pydantic validation error that
  only surfaced on live MCP calls.

### Tests / Internal
- Reconcile counts + regression goldens for the 2026-06-13 KG rebuild
  (+2 genome-only organisms, 45→47: Prochlorococcus MIT1314 / MIT1327): 5
  hard-coded integration assertions updated, 43 regression goldens
  regenerated (verified pure data drift, no structural changes).

## [0.1.0-alpha.1] - 2026-06-09
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
