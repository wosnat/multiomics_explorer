# Design: KG ↔ explorer compatibility check

**Date:** 2026-06-02
**Status:** Approved — all five design sections approved during brainstorm 2026-06-02.
**Related:**
- [2026-06-01-explorer-package-release-design.md](2026-06-01-explorer-package-release-design.md) §2 listed this as out-of-scope ("a new MCP tool `kg_release_info` returning `Schema_info` properties + a comparison verdict"). This spec is the brainstorm of that suggestion.
- KG plan `multiomics_biocypher_kg/plans/alpha_release.md` §2.1, §2.3 — the KG-side contract (`Schema_info.mcp_min_version` stamping + cross-repo coordination flow).
- `multiomics_biocypher_kg/docs/kg_mcp_guide.md` §5 — the current *manual* compatibility check (testers run a Cypher query and read the result themselves).

## 1. Overview & goal

When an alpha tester connects an explorer MCP at one version against a KG at another version, today the failure mode is silent until a tool randomly fails on an unfamiliar label or property. This spec introduces a single MCP tool, `kg_release_info`, that:

1. Reports the KG's release identity (`Schema_info` properties — version, build timestamp, counts, git identity).
2. Compares the explorer's installed version against `Schema_info.mcp_min_version` per PEP 440.
3. Walks a small set of schema-shape assertions (load-bearing node labels / relationship types / `Schema_info` properties / non-zero count sanity).
4. Returns a three-valued verdict (`ok` / `warn` / `unknown`) plus a one-line human-readable summary.

The check runs **once at MCP server startup** (in `lifespan`), the result is **cached on `KGContext`**, and the MCP tool serves the cached report on demand. The server **never refuses to start** on compat-check failure — the failure mode is "warn and continue."

## 2. Scope

**In scope:**
- New Layer 1 query builder: `kg/queries_lib.build_kg_release_info_query()`.
- New constants: `kg/constants.EXPECTED_KG_SHAPE` (5 buckets, all small).
- New Layer 2 api function: `api/functions.kg_release_info(conn) -> dict`.
- New Layer 3 MCP tool: `mcp_server/tools.kg_release_info` with `KGReleaseInfoResponse` Pydantic model.
- Lifespan extension: `KGContext` gains `kg_compat_report: dict`; lifespan runs the check after `verify_connectivity()`, caches it, logs INFO/WARN per verdict.
- MCP server `instructions` string gets one new line pointing the agent at `kg_release_info` as a "first call."
- New skill input: `inputs/tools/kg_release_info.yaml` (examples / mistakes / chaining).
- Per-layer tests at unit + live-KG integration.

**Out of scope:**
- **Strict-mode (hard-fail at startup) variant.** Decided 2026-06-02: warn-and-continue is the v1 default; strict mode is a follow-up if alpha testers report they miss warnings. Spec §3 row "Failure behavior."
- **Per-tool compat matrix.** Considered and rejected (too much code for marginal coverage beyond schema-shape sanity).
- **`_warning` envelope on every MCP tool response.** Considered and rejected. Surfacing via lifespan stderr + `kg_release_info` tool + `ctx.warning()` + MCP instructions hits the agent reliably without polluting every tool's response shape. Re-evaluate if alpha testers report missing warnings.
- **KG-side `Schema_info` schema changes.** Out of bounds — this spec consumes what the KG already stamps. KG-side work (when applicable) goes through `/release-kg` cross-repo coordination per KG plan §2.3.
- **Property-key asserts on specific nodes** (e.g. `Gene.locus_tag` exists). Too granular for v1; add via the same EXPECTED_KG_SHAPE mechanism when a regression motivates it.
- **Ontology-specific labels** (`KeggTerm`, `EcTerm`, `TcdbFamily`, etc.). Easier to fail-gracefully at query time than to assert here.
- **Bidirectional contract** (explorer declaring a min KG version). The contract direction stays as KG plan §2.3 defines it: KG declares; explorer satisfies. Re-evaluate if/when explorer features need to refuse older KGs explicitly.
- **Auto-refresh of the cached report on KG release.** Today the operator restarts the MCP after a KG upgrade; the cache is per-process. Fine for the alpha-tester flow.

## 3. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Check scope | **Version compatibility + schema-shape sanity** (not version-only; not full per-tool matrix) | Version-only misses "connected to wrong DB" / "KG missing a recent migration." Per-tool matrix is overkill for v1. Schema sanity covers 90% in 5% of the code. |
| Failure behavior | **Warn-and-continue.** Loud startup log + `ctx.warning()` on tool call. No hard-fail variant. | Alpha testers want to be unblocked; the warning has to *reach* them but not block them. Strict mode can be added (env-var-gated) when motivated by an incident. |
| Surfacing | **Dedicated MCP tool `kg_release_info` + server stderr startup log + line in MCP `instructions` pointing the agent at it.** | The MCP instructions guide the agent to call the tool on first interaction; the tool's response carries the verdict + KG identity in one place. Server stderr is the operator path. |
| Tool name | `kg_release_info` | Matches the spec §2 suggestion; honest about the dual purpose (release identity + verdict). |
| Version comparison | **PEP 440 via `packaging.version.Version`** — strict semver semantics including pre-release ordering (`0.1.0a1 < 0.1.0`). | The KG↔explorer coordination note in the explorer CHANGELOG already flagged this case; PEP 440 is the canonical Python semver. |
| Explorer version source | `importlib.metadata.version("multiomics-explorer")` | Reads from installed package metadata; works for both `uv add` installs and editable in-clone installs. |
| Cache location | `KGContext.kg_compat_report: dict` set in `lifespan` after `verify_connectivity()` | Same place the conn lives; same lifetime as the MCP process. |
| Re-evaluation | **None per session** — operator restarts the MCP after a KG upgrade | Simplest; matches the alpha-tester flow. Re-eval-on-demand is a follow-up if multi-hour sessions become common. |
| Verdict cardinality | **Three values: `ok` / `warn` / `unknown`** | `unknown` (Schema_info missing) is qualitatively different from `warn` (mismatch). Two-valued forces conflation. |
| When the check raises | **Log a WARN, set verdict=`unknown`, server still starts** | Never block startup on a defensive check. Connectivity failure remains fatal (no change). |

## 4. Architecture — layered split

Honors the project's 4-layer convention (`.claude/skills/layer-rules`):

```
Layer 1 — kg/
├── kg/constants.py
│   └── + EXPECTED_KG_SHAPE       # 5 buckets, all small tuples of strings
└── kg/queries_lib.py
    └── + build_kg_release_info_query() -> tuple[str, dict]
        # One Cypher batch: Schema_info props + db.labels() + db.relationshipTypes()

Layer 2 — api/
└── api/functions.py
    └── + kg_release_info(conn) -> dict
        # builds query, executes, reads importlib.metadata.version("multiomics-explorer"),
        # evaluates EXPECTED_KG_SHAPE, computes verdict via packaging.version.Version,
        # returns the report dict.
        # Re-exported via multiomics_explorer/__init__.py.

Layer 3 — mcp_server/
├── mcp_server/server.py
│   └── lifespan extended: after verify_connectivity, calls api.kg_release_info(conn),
│       stashes the dict on KGContext.kg_compat_report, logs INFO or WARN per verdict.
│       The check is wrapped in try/except — server still starts if the check raises.
└── mcp_server/tools.py
    └── + kg_release_info async tool — wraps the api function, validates with
        KGReleaseInfoResponse Pydantic model, await ctx.warning() if verdict != "ok"

Layer 4 — skills/
└── inputs/tools/kg_release_info.yaml
    # examples (call with no args; observe verdict on a mismatched setup)
    # mistakes (don't call on every tool — cached at startup)
    # chaining (call after MCP server boot, before doing real work)
    # Regenerated to skills/.../tools/kg_release_info.md via scripts/build_about_content.py.
```

**Why these placements:**
- `EXPECTED_KG_SHAPE` lives in `kg/constants.py` — matches existing pattern (`ALL_ONTOLOGIES`, `VALID_OG_SOURCES`, etc.).
- The check is a normal Cypher tool one level deep: one query builder + one api function + one MCP wrapper. No new top-level module.
- The lifespan's startup call goes through the api layer (not directly into queries_lib), so the cached report has the same shape the tool returns. Single source of truth.

## 5. `EXPECTED_KG_SHAPE` — the v1 assert content

```python
# kg/constants.py
EXPECTED_KG_SHAPE = {
    # 1. The contract surface — Schema_info must exist and carry these properties.
    "schema_info_required_props": (
        "version",
        "built_at",
        "mcp_min_version",
        "gene_count",
        "experiment_count",
    ),
    # 2. Foundational node labels every tool family touches.
    "required_node_labels": (
        "Schema_info",
        "Gene",
        "Experiment",
        "OrthologGroup",
        "Publication",
    ),
    # 3. Foundational relationship types.
    "required_relationship_types": (
        "Changes_expression_of",
        "Gene_in_ortholog_group",
        "Has_experiment",
    ),
    # 4. Counts that must be non-zero (catches "connected to empty DB").
    "required_nonzero_counts": (
        "gene_count",
        "experiment_count",
    ),
    # 5. Version compatibility — explorer >= Schema_info.mcp_min_version (PEP 440).
    #    Not stored in the dict; computed in api/functions.py against importlib.metadata.
}
```

Deliberate *non-inclusions* (per §2 Out of scope): per-property type/value regex checks, ontology-specific labels, BRITE/TCDB/CAZy presence, per-node property-key asserts.

## 6. Cypher (Layer 1)

`build_kg_release_info_query()` returns one batched query, ~10 lines, single round-trip:

```cypher
CALL {
  OPTIONAL MATCH (s:Schema_info {id: 'schema_info'})
  RETURN s { .* } AS schema_info
}
CALL { CALL db.labels() YIELD label
       RETURN collect(label) AS labels }
CALL { CALL db.relationshipTypes() YIELD relationshipType
       RETURN collect(relationshipType) AS rel_types }
RETURN schema_info, labels, rel_types
```

`OPTIONAL MATCH` is load-bearing on the `Schema_info` lookup: pre-2026-05-31 KGs lack the node, and we want `schema_info=null` rather than zero rows (the api function uses null as the `verdict='unknown'` trigger).

Empty params dict. No injection surface.

## 7. API function (Layer 2)

```python
# api/functions.py — sketch

from packaging.version import Version, InvalidVersion
from importlib.metadata import version as _pkg_version, PackageNotFoundError

def _get_explorer_version() -> str:
    try:
        return _pkg_version("multiomics-explorer")
    except PackageNotFoundError:
        return "unknown"

def kg_release_info(conn) -> dict:
    """Build, execute, and evaluate the KG release / compatibility check.

    Returns a dict matching the KGReleaseInfoResponse Pydantic shape:
        verdict, explorer_version, kg, asserts, summary.
    Single round-trip to the KG.
    """
    cypher, params = build_kg_release_info_query()
    rows = conn.execute_query(cypher, **params)
    row = rows[0] if rows else {"schema_info": None, "labels": [], "rel_types": []}

    schema_info = row.get("schema_info")
    labels = set(row.get("labels") or [])
    rel_types = set(row.get("rel_types") or [])

    explorer_version = _get_explorer_version()

    asserts: list[dict] = []

    if schema_info is None:
        verdict = "unknown"
        summary = (
            "UNKNOWN: Schema_info node not found "
            "(pre-2026-05-31 KG, or wrong database?)."
        )
        return {
            "verdict": verdict, "explorer_version": explorer_version,
            "kg": {}, "asserts": asserts, "summary": summary,
        }

    # Schema_info props
    for prop in EXPECTED_KG_SHAPE["schema_info_required_props"]:
        present = prop in schema_info and schema_info[prop] is not None
        asserts.append({
            "name": f"schema_info_prop:{prop}",
            "kind": "schema_info_prop",
            "passed": present,
            "detail": None if present else f"Schema_info is missing or null on '{prop}'.",
        })

    # Node labels
    for label in EXPECTED_KG_SHAPE["required_node_labels"]:
        passed = label in labels
        asserts.append({
            "name": f"node_label:{label}",
            "kind": "node_label",
            "passed": passed,
            "detail": None if passed else f"Node label '{label}' not found in db.labels().",
        })

    # Relationship types
    for rt in EXPECTED_KG_SHAPE["required_relationship_types"]:
        passed = rt in rel_types
        asserts.append({
            "name": f"relationship_type:{rt}",
            "kind": "relationship_type",
            "passed": passed,
            "detail": None if passed else f"Relationship type '{rt}' not found in db.relationshipTypes().",
        })

    # Non-zero counts
    for count_prop in EXPECTED_KG_SHAPE["required_nonzero_counts"]:
        value = schema_info.get(count_prop)
        passed = isinstance(value, int) and value > 0
        asserts.append({
            "name": f"nonzero_count:{count_prop}",
            "kind": "nonzero_count",
            "passed": passed,
            "detail": None if passed else f"Schema_info.{count_prop} is {value!r}, expected positive int.",
        })

    # Version compatibility
    kg_min = schema_info.get("mcp_min_version")
    asserts.append(_evaluate_version_compat(explorer_version, kg_min))

    failed = [a for a in asserts if not a["passed"]]
    verdict = "ok" if not failed else "warn"

    # Build summary
    if verdict == "ok":
        summary = (
            f"OK: explorer {explorer_version} satisfies KG mcp_min_version "
            f"{kg_min}; {len(asserts)}/{len(asserts)} schema asserts pass."
        )
    else:
        # Distinguish version-fail from shape-fail in the summary for clarity
        version_fail = next((a for a in failed if a["kind"] == "version_compat"), None)
        shape_fails = [a for a in failed if a["kind"] != "version_compat"]
        parts = []
        if version_fail:
            parts.append(version_fail["detail"])
        if shape_fails:
            kinds = sorted(set(a["kind"] for a in shape_fails))
            parts.append(f"{len(shape_fails)} schema assert(s) failed ({', '.join(kinds)})")
        summary = "WARN: " + "; ".join(parts) + "."

    return {
        "verdict": verdict,
        "explorer_version": explorer_version,
        "kg": {k: schema_info.get(k) for k in _KG_IDENTITY_FIELDS},
        "asserts": asserts,
        "summary": summary,
    }


def _evaluate_version_compat(explorer_version: str, kg_min: str | None) -> dict:
    """One assert dict for the version compat check."""
    name = "version_compat"
    if kg_min is None:
        return {"name": name, "kind": "version_compat", "passed": False,
                "detail": "KG did not declare mcp_min_version."}
    try:
        ev = Version(explorer_version)
        kv = Version(kg_min)
    except InvalidVersion as e:
        return {"name": name, "kind": "version_compat", "passed": False,
                "detail": f"Could not parse a version: {e}."}
    if ev >= kv:
        return {"name": name, "kind": "version_compat", "passed": True, "detail": None}
    return {"name": name, "kind": "version_compat", "passed": False,
            "detail": f"Explorer {explorer_version} < KG mcp_min_version {kg_min} (PEP 440)."}


_KG_IDENTITY_FIELDS = (
    "version", "built_at", "mcp_min_version", "git_sha_short", "git_branch",
    "gene_count", "experiment_count", "paper_count", "organism_count",
    "expression_edge_count", "release_notes_url",
)
```

The version-compat helper is factored out so it gets its own dedicated unit test (the explorer ↔ KG pre-release coordination case — see §10).

## 8. MCP tool (Layer 3) — return shape

```python
# mcp_server/tools.py — sketch (imports omitted)

class KGAssert(BaseModel):
    name: str = Field(description="Stable identifier, e.g. 'node_label:Gene' or 'schema_info_prop:gene_count' or 'nonzero_count:gene_count' or 'version_compat'.")
    kind: Literal[
        "schema_info_prop", "node_label", "relationship_type",
        "nonzero_count", "version_compat",
    ] = Field(description="Which assertion family this belongs to.")
    passed: bool = Field(description="True if the assertion held against the live KG.")
    detail: str | None = Field(default=None, description="Human-readable explanation when failed; null when passed.")


class KGIdentity(BaseModel):
    """Schema_info node properties — the KG's self-declared release identity.
    Mostly-null on verdict='unknown'."""
    version: str | None = Field(default=None, description="KG release version (e.g. '0.1.0-alpha.1'); '0.0.0-dev' on dev builds.")
    built_at: str | None = Field(default=None, description="ISO-8601 UTC build timestamp.")
    mcp_min_version: str | None = Field(default=None, description="Minimum compatible explorer-MCP version (PEP 440 / semver). The contract surface.")
    git_sha_short: str | None = Field(default=None)
    git_branch: str | None = Field(default=None)
    gene_count: int | None = Field(default=None)
    experiment_count: int | None = Field(default=None)
    paper_count: int | None = Field(default=None)
    organism_count: int | None = Field(default=None)
    expression_edge_count: int | None = Field(default=None)
    release_notes_url: str | None = Field(default=None)


class KGReleaseInfoResponse(BaseModel):
    verdict: Literal["ok", "warn", "unknown"] = Field(
        description=(
            "'ok' = explorer version satisfies KG.mcp_min_version AND all schema asserts pass. "
            "'warn' = at least one assert failed; tools still work but may emit confusing errors. "
            "'unknown' = check could not be evaluated (Schema_info missing — pre-2026-05-31 KG, or wrong DB)."
        )
    )
    explorer_version: str = Field(description="Installed multiomics-explorer version (PEP 440 form, e.g. '0.1.0a1').")
    kg: KGIdentity = Field(description="The KG's self-declared release identity.")
    asserts: list[KGAssert] = Field(description="Every assertion evaluated, pass + fail. Filter `passed=False` for the failure list.")
    summary: str = Field(description="One-line human-readable verdict.")


@mcp.tool()
async def kg_release_info(ctx: Context) -> KGReleaseInfoResponse:
    """Return the KG's release identity and a compatibility verdict against
    this explorer-MCP version. Cached at MCP startup — re-call is instant."""
    report = ctx.request_context.lifespan_context.kg_compat_report
    response = KGReleaseInfoResponse(**report)
    if response.verdict != "ok":
        await ctx.warning(response.summary)
    return response
```

Tool registry assertion bumps from 39 → 40 (see §9 testing).

## 9. Lifespan + MCP instructions (Layer 3 wiring)

### 9.1 `KGContext` + `lifespan`

```python
# mcp_server/server.py — sketch

@dataclass
class KGContext:
    conn: GraphConnection
    kg_compat_report: dict  # api.kg_release_info shape, cached


@asynccontextmanager
async def lifespan(server: FastMCP):
    settings = get_settings()
    conn = GraphConnection(settings)
    if not conn.verify_connectivity():
        raise RuntimeError(f"Cannot connect to Neo4j at {settings.neo4j_uri}")
    logger.info("Connected to Neo4j at %s", settings.neo4j_uri)

    try:
        report = kg_release_info(conn)   # api/ function
    except Exception as e:
        logger.warning("KG compatibility check failed to evaluate: %s", e)
        report = {
            "verdict": "unknown",
            "summary": f"Check could not run: {e}",
            "explorer_version": _get_explorer_version(),
            "kg": {},
            "asserts": [],
        }

    if report["verdict"] == "ok":
        logger.info("KG compat: %s", report["summary"])
    else:
        logger.warning("KG compat: %s", report["summary"])

    try:
        yield KGContext(conn=conn, kg_compat_report=report)
    finally:
        conn.close()
        logger.info("Neo4j connection closed")
```

**Guarantees:** server starts even if the check raises. Connectivity failure remains fatal (no change). Compat failure is loud-but-non-blocking.

### 9.2 MCP `instructions` update

Add one line near the top of the existing instructions block at [server.py:42-64](../../../multiomics_explorer/mcp_server/server.py#L42-L64):

```
First call: kg_release_info — verifies your KG release matches what this
explorer-MCP version expects. Surfaces the KG's identity (version, built_at,
counts) and a verdict (ok / warn / unknown).
```

This is the discoverability hook. The agent reads instructions when the MCP server registers; the line appears alongside the existing `docs://guide/start_here` etc. orientation.

### 9.3 What the alpha tester sees end-to-end

| Path | Where the message appears |
|---|---|
| Operator running `uv run multiomics-kg-mcp` from a terminal | One INFO or WARN line on stderr at startup, with `summary` text. |
| Claude Code session, agent reads MCP instructions on connect | Sees "First call: kg_release_info" → calls it → gets the response + `ctx.warning()` if non-ok. |
| Tester asks the agent "is everything ok?" mid-session | Agent calls `kg_release_info` (cached startup report; instant). Same response. |
| Future-self running tests via Python API | `from multiomics_explorer import kg_release_info; kg_release_info(conn)` — same shape, no warning rail (no `ctx` in plain Python). |

## 10. Testing approach (Layer 1–4)

| Layer | Test file | What's covered |
|---|---|---|
| 1. `kg/queries_lib.py` | `tests/unit/test_query_builders.py` | Snapshot of `build_kg_release_info_query()` — Cypher string + empty params dict. Pure unit, no DB. |
| 1. `kg/constants.py` (drift) | `tests/integration/test_kg_constants_drift.py` (existing file, KG-marked) | Add a new test: every label / relationship type / `Schema_info` property named in `EXPECTED_KG_SHAPE` is present in the live KG. Same shape and intent as the existing `VALID_CLUSTER_TYPES` etc. drift tests. Catches "we updated the KG schema and forgot to update the constant" — the same pattern that drives the existing drift suite. |
| 2. `api/functions.py` | `tests/unit/test_api_contract.py` + `tests/integration/test_api_contract.py` | Unit: mock `conn.execute_query` returning synthetic rows for 4 scenarios — `ok`, `warn-version`, `warn-shape`, `unknown` (missing `Schema_info`). Integration (`@pytest.mark.kg`): call against live dev KG; assert `verdict='ok'`, `kg.version` present, `kg.gene_count > 0`. |
| 2. **Semver edge case** | same unit file, dedicated test | `_evaluate_version_compat("0.1.0a1", "0.1.0")` → `passed=False, detail` mentions "PEP 440." This is *the* case the explorer↔KG coordination note in the changelog flagged. Must have an explicit test. |
| 3. `mcp_server/tools.py` | `tests/unit/test_tool_wrappers.py` | `KGReleaseInfoResponse(**report)` validates for `ok` / `warn` / `unknown` shapes. `EXPECTED_TOOLS` registry gains `"kg_release_info"`. The existing `test_expected_tools_size_unchanged_at_39` (size-pinning regression test) must be renamed and bumped to `_at_40`. |
| 3. Live KG smoke | `tests/integration/test_mcp_tools.py` | `kg_release_info` MCP tool called via FastMCP test client returns `verdict='ok'` against live dev KG. |
| 4. Skill content | `tests/integration/test_about_examples.py` | `inputs/tools/kg_release_info.yaml` exists and parses; regenerated MD up-to-date (lint-mode check). |

**Lifespan test:** skipped at unit level — too much mocking for too little signal. The live-KG integration test exercises the full lifespan path (boot the MCP, call the tool, assert response). Sufficient coverage.

**Version-of-explorer assertion:** the integration test pins one expected fact: `response.explorer_version == importlib.metadata.version("multiomics-explorer")`. Catches the rare case where the lookup function changes shape.

**Regression after KG bumps mcp_min_version:** the live-KG integration test will start failing if the dev KG's `mcp_min_version` floats above the installed explorer. That's a feature — it surfaces the exact contract-divergence we want to catch.

## 11. Verification & acceptance

1. **Lifespan boots cleanly** against the live dev KG; stderr has one `INFO  KG compat: OK: explorer 0.1.0a1 satisfies KG mcp_min_version 0.1.0; 16/16 schema asserts pass.` line.
2. **Tool call returns `verdict='ok'`** via FastMCP test client against the dev KG.
3. **EXPECTED_KG_SHAPE walk produces 16 asserts:** 5 `schema_info_prop` + 5 `node_label` + 3 `relationship_type` + 2 `nonzero_count` + 1 `version_compat`. `gene_count` and `experiment_count` appear in two buckets (`schema_info_prop:gene_count` vs `nonzero_count:gene_count`) but are evaluated as distinct asserts under distinct names. The total count is a unit-test invariant.
4. **PEP 440 unit test passes** for `("0.1.0a1", "0.1.0") → fail`, `("0.1.0", "0.1.0") → pass`, `("0.2.0", "0.1.0") → pass`, `("0.1.0a1", "0.1.0a1") → pass`.
5. **`unknown` verdict path** triggers when synthetic rows return `schema_info=None`. Unit test confirms `kg` field is `{}` and asserts list is `[]`.
6. **Lifespan robustness:** if `kg_release_info(conn)` raises, server still starts; logged WARN with the exception text; `KGContext.kg_compat_report` carries `verdict='unknown'`.
7. **Tool docs regenerated:** `uv run python scripts/build_about_content.py` writes `skills/multiomics-kg-guide/references/tools/kg_release_info.md`, and `--lint kg_release_info` is green.
8. **`importlib.metadata` lookup works** in both `uv add` install and editable in-clone install paths (the regression target — the version source is the only place this can silently misbehave).

## 12. Cross-repo coordination implications

When `Schema_info.mcp_min_version` is bumped on the KG side (e.g., a KG release that introduces a new required label), this check will start emitting `verdict='warn'` against any older explorer. That's the intended signal. The KG plan §2.3 already documents the coordination dance:

> When a change genuinely spans both repos, cut an explorer release first, bump `--mcp-min`, then cut the KG release.

This spec is the explorer-side surface that makes the divergence *visible* to the alpha tester. It does not automate the coordination — that stays as the operator's release-time judgment.

## 13. Out-of-scope follow-ups (post-v1)

- **Strict-mode env-var override** (`EXPLORER_STRICT_KG_CHECK=1` → hard-fail at startup). Add when warn-mode misses a failure that bit a tester.
- **`_warning` envelope on every MCP tool response.** Add if alpha testers report they don't see the kg_release_info warning.
- **Lazy re-evaluation on demand** (`kg_release_info(refresh=True)`). Add when multi-hour sessions become common.
- **Per-tool compat matrix** (each MCP tool declares its KG shape dependencies). Add when EXPECTED_KG_SHAPE drift becomes a maintenance burden.
- **Bidirectional contract** (explorer declares `kg_min_version`). Add when an explorer feature needs to refuse older KGs explicitly.
- **Property-key asserts on specific nodes** and **ontology-specific labels in EXPECTED_KG_SHAPE.** Add via the same mechanism when a regression motivates each.
