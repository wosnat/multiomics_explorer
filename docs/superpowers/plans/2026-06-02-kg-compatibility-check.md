# KG Compatibility Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `kg_release_info` MCP tool that surfaces the KG's release identity and a compatibility verdict (`ok` / `warn` / `unknown`) against the installed explorer-MCP version, per the 2026-06-02 design spec.

**Architecture:** 4-layer split following `.claude/skills/layer-rules`. Layer 1: `kg/constants.EXPECTED_KG_SHAPE` + `kg/queries_lib.build_kg_release_info_query()`. Layer 2: `api/functions.kg_release_info()` + `_evaluate_version_compat()` helper. Layer 3: `mcp_server/tools.kg_release_info` MCP tool + `KGReleaseInfoResponse` Pydantic model + lifespan caching on `KGContext.kg_compat_report`. Layer 4: `inputs/tools/kg_release_info.yaml` source for regenerated skill MD. Failure mode is warn-and-continue; the report is computed once at lifespan startup and served from cache; version comparison uses `packaging.version.Version` (PEP 440 semantics — `0.1.0a1 < 0.1.0` is the load-bearing edge case).

**Tech Stack:** Python 3.11+; Neo4j (read-only Cypher); `packaging.version` (already transitive via pydantic — verified `from packaging.version import Version` imports in this venv); `pydantic` v2; FastMCP 3.x; pytest 9; `importlib.metadata`. No new runtime dependencies.

**Spec:** [`docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md`](../specs/2026-06-02-kg-compatibility-check-design.md)

---

## Task 1: Add `EXPECTED_KG_SHAPE` to `kg/constants.py`

**Files:**
- Modify: `multiomics_explorer/kg/constants.py` (append after existing constants)

Pure data addition — no behavior to TDD. The drift test in Task 8 exercises this against the live KG; nothing to test in isolation.

- [ ] **Step 1: Append the constant**

Open `multiomics_explorer/kg/constants.py` and append at the end:

```python


# Schema-shape contract for the KG ↔ explorer compatibility check
# (api/functions.kg_release_info). Five buckets, all small. Bucket 5
# (version compatibility) is computed in api/functions.py, not stored here.
# See docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md §5.
EXPECTED_KG_SHAPE: dict[str, tuple[str, ...]] = {
    "schema_info_required_props": (
        "version",
        "built_at",
        "mcp_min_version",
        "gene_count",
        "experiment_count",
    ),
    "required_node_labels": (
        "Schema_info",
        "Gene",
        "Experiment",
        "OrthologGroup",
        "Publication",
    ),
    "required_relationship_types": (
        "Changes_expression_of",
        "Gene_in_ortholog_group",
        "Has_experiment",
    ),
    "required_nonzero_counts": (
        "gene_count",
        "experiment_count",
    ),
}
```

- [ ] **Step 2: Verify the module still imports**

Run: `uv run python -c "from multiomics_explorer.kg.constants import EXPECTED_KG_SHAPE; print(sorted(EXPECTED_KG_SHAPE.keys()))"`
Expected: `['required_node_labels', 'required_nonzero_counts', 'required_relationship_types', 'schema_info_required_props']`

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/kg/constants.py
git commit -m "kg(constants): add EXPECTED_KG_SHAPE for compatibility check"
```

---

## Task 2: `build_kg_release_info_query()` query builder (Layer 1, TDD)

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (add at end of file, near other query builders)
- Modify: `tests/unit/test_query_builders.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_query_builders.py`:

```python
class TestBuildKGReleaseInfoQuery:
    """Layer-1 builder for the kg_release_info compatibility check."""

    def test_returns_cypher_and_empty_params(self):
        from multiomics_explorer.kg.queries_lib import build_kg_release_info_query

        cypher, params = build_kg_release_info_query()
        assert isinstance(cypher, str)
        assert params == {}

    def test_cypher_pulls_schema_info_optional_match(self):
        from multiomics_explorer.kg.queries_lib import build_kg_release_info_query

        cypher, _ = build_kg_release_info_query()
        # OPTIONAL MATCH is load-bearing: pre-2026-05-31 KGs have no
        # Schema_info node and we want a null row, not an empty result.
        assert "OPTIONAL MATCH (s:Schema_info" in cypher
        assert "id: 'schema_info'" in cypher

    def test_cypher_collects_labels_and_relationship_types(self):
        from multiomics_explorer.kg.queries_lib import build_kg_release_info_query

        cypher, _ = build_kg_release_info_query()
        assert "CALL db.labels()" in cypher
        assert "CALL db.relationshipTypes()" in cypher

    def test_cypher_returns_three_aliases(self):
        from multiomics_explorer.kg.queries_lib import build_kg_release_info_query

        cypher, _ = build_kg_release_info_query()
        # Three top-level RETURN aliases that api/functions.kg_release_info
        # destructures: schema_info, labels, rel_types.
        assert "schema_info" in cypher
        assert "AS labels" in cypher
        assert "AS rel_types" in cypher
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_query_builders.py::TestBuildKGReleaseInfoQuery -v`
Expected: FAIL with `ImportError: cannot import name 'build_kg_release_info_query'` (or `AttributeError`).

- [ ] **Step 3: Implement the query builder**

Append to `multiomics_explorer/kg/queries_lib.py`:

```python


def build_kg_release_info_query() -> tuple[str, dict]:
    """Cypher for the KG release identity + schema-shape compat check.

    Single round-trip; OPTIONAL MATCH on Schema_info so pre-2026-05-31
    KGs (no Schema_info node) return a null `schema_info` rather than
    zero rows. The api-layer caller treats null as verdict='unknown'.

    See docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md §6.
    """
    cypher = """
CALL {
  OPTIONAL MATCH (s:Schema_info {id: 'schema_info'})
  RETURN s { .* } AS schema_info
}
CALL { CALL db.labels() YIELD label
       RETURN collect(label) AS labels }
CALL { CALL db.relationshipTypes() YIELD relationshipType
       RETURN collect(relationshipType) AS rel_types }
RETURN schema_info, labels, rel_types
"""
    return cypher.strip(), {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_query_builders.py::TestBuildKGReleaseInfoQuery -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "kg(queries_lib): build_kg_release_info_query for compat check"
```

---

## Task 3: `_evaluate_version_compat()` helper (Layer 2, TDD with PEP 440 edge cases)

**Files:**
- Modify: `multiomics_explorer/api/functions.py` (add at top with other helpers; or end if no helper section)
- Modify: `tests/unit/test_api_functions.py` (add test class)

The PEP 440 pre-release edge case (`0.1.0a1 < 0.1.0`) is *the* explorer↔KG coordination case the CHANGELOG already flagged. It must have an explicit test.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_api_functions.py`:

```python
class TestEvaluateVersionCompat:
    """The version_compat assert dict, including PEP 440 pre-release semantics."""

    def test_kg_min_none_fails(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.1.0", None)
        assert result["name"] == "version_compat"
        assert result["kind"] == "version_compat"
        assert result["passed"] is False
        assert "did not declare mcp_min_version" in result["detail"]

    def test_pre_release_explorer_against_stable_min_fails(self):
        """The load-bearing case: explorer 0.1.0a1 against KG mcp_min_version 0.1.0.
        PEP 440 says 0.1.0a1 < 0.1.0 (pre-release ordering)."""
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.1.0a1", "0.1.0")
        assert result["passed"] is False
        assert "0.1.0a1" in result["detail"]
        assert "0.1.0" in result["detail"]
        assert "PEP 440" in result["detail"]

    def test_equal_versions_pass(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.1.0", "0.1.0")
        assert result["passed"] is True
        assert result["detail"] is None

    def test_explorer_newer_than_min_passes(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.2.0", "0.1.0")
        assert result["passed"] is True

    def test_matching_pre_releases_pass(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.1.0a1", "0.1.0a1")
        assert result["passed"] is True

    def test_invalid_version_string_fails_gracefully(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("not-a-version", "0.1.0")
        assert result["passed"] is False
        assert "Could not parse" in result["detail"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_functions.py::TestEvaluateVersionCompat -v`
Expected: FAIL with `ImportError: cannot import name '_evaluate_version_compat'`.

- [ ] **Step 3: Implement the helper**

Append to `multiomics_explorer/api/functions.py` (add the imports at the top of the file if missing):

```python
# Add to imports at top (or near other typing imports):
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from packaging.version import InvalidVersion, Version
```

Then append (e.g., near the bottom of the module, with other module-private helpers):

```python


# --- kg_release_info helpers (compat check) ----------------------------------

_KG_IDENTITY_FIELDS = (
    "version", "built_at", "mcp_min_version", "git_sha_short", "git_branch",
    "gene_count", "experiment_count", "paper_count", "organism_count",
    "expression_edge_count", "release_notes_url",
)


def _get_explorer_version() -> str:
    """Return the installed multiomics-explorer version via importlib.metadata.

    Returns 'unknown' if the package metadata cannot be located (rare —
    only when running against a tree that was never installed via uv/pip)."""
    try:
        return _pkg_version("multiomics-explorer")
    except PackageNotFoundError:
        return "unknown"


def _evaluate_version_compat(explorer_version: str, kg_min: str | None) -> dict:
    """Build the version_compat assert dict.

    PEP 440 semantics — `0.1.0a1 < 0.1.0` (pre-release < release).
    This is the explorer↔KG coordination edge case the CHANGELOG flagged.
    """
    name = "version_compat"
    if kg_min is None:
        return {
            "name": name, "kind": "version_compat", "passed": False,
            "detail": "KG did not declare mcp_min_version.",
        }
    try:
        ev = Version(explorer_version)
        kv = Version(kg_min)
    except InvalidVersion as e:
        return {
            "name": name, "kind": "version_compat", "passed": False,
            "detail": f"Could not parse a version: {e}.",
        }
    if ev >= kv:
        return {"name": name, "kind": "version_compat", "passed": True, "detail": None}
    return {
        "name": name, "kind": "version_compat", "passed": False,
        "detail": f"Explorer {explorer_version} < KG mcp_min_version {kg_min} (PEP 440).",
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_functions.py::TestEvaluateVersionCompat -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "api(functions): _evaluate_version_compat helper (PEP 440) for compat check"
```

---

## Task 4: `kg_release_info()` api function (Layer 2, TDD with 4 scenarios)

**Files:**
- Modify: `multiomics_explorer/api/functions.py` (add `kg_release_info` next to the helpers from Task 3)
- Modify: `multiomics_explorer/__init__.py` (re-export `kg_release_info`)
- Modify: `tests/unit/test_api_functions.py` (add test class)

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_api_functions.py`:

```python
class TestKGReleaseInfo:
    """The api-layer kg_release_info function — 4 scenarios via mocked conn."""

    def _make_conn(self, schema_info, labels, rel_types):
        """Build a fake conn whose execute_query returns one row of the
        build_kg_release_info_query() shape."""
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute_query.return_value = [{
            "schema_info": schema_info,
            "labels": labels,
            "rel_types": rel_types,
        }]
        return conn

    def _ok_schema_info(self, **overrides):
        si = {
            "version": "0.1.0",
            "built_at": "2026-06-02T00:00:00Z",
            "mcp_min_version": "0.0.1",
            "git_sha_short": "deadbee",
            "git_branch": "main",
            "gene_count": 100,
            "experiment_count": 5,
            "paper_count": 3,
            "organism_count": 2,
            "expression_edge_count": 500,
            "release_notes_url": None,
        }
        si.update(overrides)
        return si

    def _ok_labels(self):
        return ["Schema_info", "Gene", "Experiment", "OrthologGroup", "Publication", "Other"]

    def _ok_rel_types(self):
        return ["Changes_expression_of", "Gene_in_ortholog_group", "Has_experiment", "Other"]

    def test_ok_verdict_when_everything_passes(self):
        from multiomics_explorer.api.functions import kg_release_info
        conn = self._make_conn(self._ok_schema_info(), self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["verdict"] == "ok"
        # 5 + 5 + 3 + 2 + 1 = 16 asserts
        assert len(report["asserts"]) == 16
        assert all(a["passed"] for a in report["asserts"])
        assert "OK:" in report["summary"]
        assert report["kg"]["version"] == "0.1.0"
        assert report["explorer_version"]  # populated, real value

    def test_warn_verdict_on_version_mismatch(self):
        from multiomics_explorer.api.functions import kg_release_info
        # KG demands a version higher than anything the explorer could be
        si = self._ok_schema_info(mcp_min_version="99.99.99")
        conn = self._make_conn(si, self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["verdict"] == "warn"
        version_assert = next(a for a in report["asserts"] if a["kind"] == "version_compat")
        assert version_assert["passed"] is False
        assert "99.99.99" in version_assert["detail"]
        assert "WARN:" in report["summary"]

    def test_warn_verdict_on_missing_label(self):
        from multiomics_explorer.api.functions import kg_release_info
        labels = ["Schema_info", "Gene", "Experiment", "OrthologGroup"]  # Publication missing
        conn = self._make_conn(self._ok_schema_info(), labels, self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["verdict"] == "warn"
        pub_assert = next(a for a in report["asserts"] if a["name"] == "node_label:Publication")
        assert pub_assert["passed"] is False

    def test_unknown_verdict_when_schema_info_missing(self):
        from multiomics_explorer.api.functions import kg_release_info
        conn = self._make_conn(None, [], [])

        report = kg_release_info(conn)

        assert report["verdict"] == "unknown"
        assert report["kg"] == {}
        assert report["asserts"] == []
        assert "UNKNOWN:" in report["summary"]
        assert "Schema_info node not found" in report["summary"]
        assert report["explorer_version"]  # still populated

    def test_kg_identity_only_carries_known_fields(self):
        """KGIdentity is the curated subset, not all Schema_info props."""
        from multiomics_explorer.api.functions import kg_release_info
        si = self._ok_schema_info()
        si["some_extra_prop"] = "should-not-appear"
        conn = self._make_conn(si, self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert "some_extra_prop" not in report["kg"]
        assert "version" in report["kg"]
        assert "gene_count" in report["kg"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_functions.py::TestKGReleaseInfo -v`
Expected: FAIL with `ImportError: cannot import name 'kg_release_info'`.

- [ ] **Step 3: Implement `kg_release_info`**

Append to `multiomics_explorer/api/functions.py` (after the helpers from Task 3):

```python


def kg_release_info(conn) -> dict:
    """Compute the KG release identity + compatibility verdict.

    One Cypher round-trip; pure Python evaluation of EXPECTED_KG_SHAPE.
    Returns a dict matching the KGReleaseInfoResponse Pydantic shape
    (verdict, explorer_version, kg, asserts, summary). Cached by the
    MCP server at lifespan startup; the kg_release_info MCP tool reads
    from cache.

    See docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md §7.
    """
    from multiomics_explorer.kg.constants import EXPECTED_KG_SHAPE
    from multiomics_explorer.kg.queries_lib import build_kg_release_info_query

    cypher, params = build_kg_release_info_query()
    rows = conn.execute_query(cypher, **params)
    row = rows[0] if rows else {"schema_info": None, "labels": [], "rel_types": []}

    schema_info = row.get("schema_info")
    labels = set(row.get("labels") or [])
    rel_types = set(row.get("rel_types") or [])

    explorer_version = _get_explorer_version()

    # No Schema_info node -> verdict='unknown', short-circuit
    if schema_info is None:
        return {
            "verdict": "unknown",
            "explorer_version": explorer_version,
            "kg": {},
            "asserts": [],
            "summary": (
                "UNKNOWN: Schema_info node not found "
                "(pre-2026-05-31 KG, or wrong database?)."
            ),
        }

    asserts: list[dict] = []

    for prop in EXPECTED_KG_SHAPE["schema_info_required_props"]:
        present = prop in schema_info and schema_info[prop] is not None
        asserts.append({
            "name": f"schema_info_prop:{prop}",
            "kind": "schema_info_prop",
            "passed": present,
            "detail": None if present else f"Schema_info is missing or null on '{prop}'.",
        })

    for label in EXPECTED_KG_SHAPE["required_node_labels"]:
        passed = label in labels
        asserts.append({
            "name": f"node_label:{label}",
            "kind": "node_label",
            "passed": passed,
            "detail": None if passed else f"Node label '{label}' not found in db.labels().",
        })

    for rt in EXPECTED_KG_SHAPE["required_relationship_types"]:
        passed = rt in rel_types
        asserts.append({
            "name": f"relationship_type:{rt}",
            "kind": "relationship_type",
            "passed": passed,
            "detail": None if passed else f"Relationship type '{rt}' not found in db.relationshipTypes().",
        })

    for count_prop in EXPECTED_KG_SHAPE["required_nonzero_counts"]:
        value = schema_info.get(count_prop)
        passed = isinstance(value, int) and value > 0
        asserts.append({
            "name": f"nonzero_count:{count_prop}",
            "kind": "nonzero_count",
            "passed": passed,
            "detail": None if passed else f"Schema_info.{count_prop} is {value!r}, expected positive int.",
        })

    kg_min = schema_info.get("mcp_min_version")
    asserts.append(_evaluate_version_compat(explorer_version, kg_min))

    failed = [a for a in asserts if not a["passed"]]
    verdict = "ok" if not failed else "warn"

    if verdict == "ok":
        summary = (
            f"OK: explorer {explorer_version} satisfies KG mcp_min_version "
            f"{kg_min}; {len(asserts)}/{len(asserts)} schema asserts pass."
        )
    else:
        version_fail = next((a for a in failed if a["kind"] == "version_compat"), None)
        shape_fails = [a for a in failed if a["kind"] != "version_compat"]
        parts: list[str] = []
        if version_fail:
            parts.append(version_fail["detail"].rstrip("."))
        if shape_fails:
            kinds = sorted({a["kind"] for a in shape_fails})
            parts.append(
                f"{len(shape_fails)} schema assert(s) failed ({', '.join(kinds)})"
            )
        summary = "WARN: " + "; ".join(parts) + "."

    return {
        "verdict": verdict,
        "explorer_version": explorer_version,
        "kg": {k: schema_info.get(k) for k in _KG_IDENTITY_FIELDS},
        "asserts": asserts,
        "summary": summary,
    }
```

- [ ] **Step 4: Re-export from the package root**

Open `multiomics_explorer/__init__.py` and add to the existing re-export block:

```python
from multiomics_explorer.api.functions import kg_release_info  # noqa: F401
```

(Place alongside the other `from multiomics_explorer.api.functions import ...` lines.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_functions.py::TestKGReleaseInfo -v`
Expected: 5 passed.

- [ ] **Step 6: Sanity-check the re-export**

Run: `uv run python -c "from multiomics_explorer import kg_release_info; print(kg_release_info.__module__)"`
Expected: `multiomics_explorer.api.functions`

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/__init__.py tests/unit/test_api_functions.py
git commit -m "api(functions): kg_release_info — main check (verdict + identity + asserts)"
```

---

## Task 5: MCP tool wrapper + Pydantic models (Layer 3, TDD)

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` (add models + tool; add `"kg_release_info"` to `EXPECTED_TOOLS` if there's a per-module registry — confirm via Step 1)
- Modify: `tests/unit/test_tool_wrappers.py` — add tests; add `"kg_release_info"` to `EXPECTED_TOOLS` list (line 49); rename the size-pinning regression test from `..._at_39` → `..._at_40` and update its assertion

- [ ] **Step 1: Confirm the registration pattern (already discovered)**

Project pattern, verified in `multiomics_explorer/mcp_server/tools.py`:

1. **Pydantic response models** can be defined at **module level** (e.g. `PathwayEnrichmentResult` at line 28 — comment says "module-level for direct importability"). Module-level is required here because `tests/unit/test_tool_wrappers.py` imports `KGReleaseInfoResponse` directly.
2. **All `@mcp.tool(...)` registrations** live inside `def register_tools(mcp: FastMCP):` starting at line 1245. (Pydantic models for tools that don't need test-import can also live inside this function, like `KgSchemaResponse` at line 1248 — but ours are module-level.)
3. **Connection access** is via the helper `_conn(ctx)` at line 18: `return ctx.request_context.lifespan_context.conn`. For `kg_release_info` we need an analogous helper for the cached report.
4. **Decorator style:** `@mcp.tool(tags={...}, annotations={...})` with the tags + readOnly/destructive/idempotent/openWorld annotations dict — see kg_schema at line 1259 as the closest analog.
5. **Error pattern:** `try/except` with `await ctx.error(...)` + `raise ToolError(...)`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/unit/test_tool_wrappers.py`:

```python
class TestKGReleaseInfoTool:
    """Layer-3 wrapper for kg_release_info — Pydantic shape validation."""

    def _ok_report(self):
        return {
            "verdict": "ok",
            "explorer_version": "0.1.0a1",
            "kg": {
                "version": "0.1.0",
                "built_at": "2026-06-02T00:00:00Z",
                "mcp_min_version": "0.0.1",
                "git_sha_short": "deadbee",
                "git_branch": "main",
                "gene_count": 100,
                "experiment_count": 5,
                "paper_count": 3,
                "organism_count": 2,
                "expression_edge_count": 500,
                "release_notes_url": None,
            },
            "asserts": [
                {"name": "version_compat", "kind": "version_compat", "passed": True, "detail": None},
            ],
            "summary": "OK: explorer 0.1.0a1 satisfies KG mcp_min_version 0.0.1; 1/1 asserts pass.",
        }

    def test_response_validates_ok_shape(self):
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        response = KGReleaseInfoResponse(**self._ok_report())
        assert response.verdict == "ok"
        assert response.kg.version == "0.1.0"
        assert len(response.asserts) == 1

    def test_response_validates_warn_shape(self):
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        report = self._ok_report()
        report["verdict"] = "warn"
        report["asserts"] = [
            {"name": "version_compat", "kind": "version_compat", "passed": False,
             "detail": "Explorer 0.1.0a1 < KG mcp_min_version 99.99.99 (PEP 440)."},
        ]
        response = KGReleaseInfoResponse(**report)
        assert response.verdict == "warn"
        assert response.asserts[0].passed is False

    def test_response_validates_unknown_shape(self):
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        unknown = {
            "verdict": "unknown",
            "explorer_version": "0.1.0a1",
            "kg": {},  # all defaults to None
            "asserts": [],
            "summary": "UNKNOWN: Schema_info node not found.",
        }
        response = KGReleaseInfoResponse(**unknown)
        assert response.verdict == "unknown"
        assert response.kg.version is None
        assert response.asserts == []

    def test_response_rejects_unknown_verdict(self):
        from pydantic import ValidationError
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        bad = self._ok_report()
        bad["verdict"] = "bogus"
        try:
            KGReleaseInfoResponse(**bad)
        except ValidationError:
            return
        raise AssertionError("Expected ValidationError on bogus verdict")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tool_wrappers.py::TestKGReleaseInfoTool -v`
Expected: FAIL with `ImportError: cannot import name 'KGReleaseInfoResponse'`.

- [ ] **Step 4: Implement the Pydantic models at module level**

In `multiomics_explorer/mcp_server/tools.py`, add the three Pydantic models at module level — same level as `PathwayEnrichmentResult` (around line 28). Place them after the existing module-level models:

```python
class KGAssert(BaseModel):
    """One element of the kg_release_info schema-shape assertion checklist."""
    name: str = Field(
        description="Stable identifier, e.g. 'node_label:Gene' or 'schema_info_prop:gene_count' or 'nonzero_count:gene_count' or 'version_compat'."
    )
    kind: Literal[
        "schema_info_prop", "node_label", "relationship_type",
        "nonzero_count", "version_compat",
    ] = Field(description="Which assertion family this belongs to.")
    passed: bool = Field(description="True if the assertion held against the live KG.")
    detail: str | None = Field(
        default=None,
        description="Human-readable explanation when failed; null when passed.",
    )


class KGIdentity(BaseModel):
    """Schema_info node properties — the KG's self-declared release identity.
    Mostly-null on verdict='unknown'."""
    version: str | None = Field(default=None, description="KG release version (e.g. '0.1.0-alpha.1'); '0.0.0-dev' on dev builds.")
    built_at: str | None = Field(default=None, description="ISO-8601 UTC build timestamp.")
    mcp_min_version: str | None = Field(default=None, description="Minimum compatible explorer-MCP version (PEP 440 / semver). The contract surface.")
    git_sha_short: str | None = Field(default=None, description="Short git SHA of the KG build.")
    git_branch: str | None = Field(default=None, description="Git branch of the KG build.")
    gene_count: int | None = Field(default=None, description="Number of Gene nodes in the KG.")
    experiment_count: int | None = Field(default=None, description="Number of Experiment nodes in the KG.")
    paper_count: int | None = Field(default=None, description="Number of Publication nodes in the KG.")
    organism_count: int | None = Field(default=None, description="Number of OrganismTaxon nodes in the KG.")
    expression_edge_count: int | None = Field(default=None, description="Number of Changes_expression_of edges in the KG.")
    release_notes_url: str | None = Field(default=None, description="URL of the KG release notes, when stamped.")


class KGReleaseInfoResponse(BaseModel):
    """Response for the kg_release_info tool — release identity + compat verdict."""
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
```

`Literal` and `Field` are already imported at [tools.py:5,9](multiomics_explorer/mcp_server/tools.py#L5) — no import changes needed at module top.

- [ ] **Step 4b: Add the `_kg_compat_report(ctx)` helper**

Just below the existing `_conn(ctx)` helper at [tools.py:18-20](multiomics_explorer/mcp_server/tools.py#L18-L20), add:

```python
def _kg_compat_report(ctx: Context) -> dict:
    """Get the cached KG compatibility report from lifespan context.

    Computed once in mcp_server/server.py:lifespan; the kg_release_info
    tool reads from this cache."""
    return ctx.request_context.lifespan_context.kg_compat_report
```

- [ ] **Step 4c: Add the `@mcp.tool` registration inside `register_tools()`**

Inside `def register_tools(mcp: FastMCP):` (starts at line 1245), add the new tool right after the `kg_schema` tool (so it sits next to the other top-level introspection tool). Match the decorator style of `kg_schema` at line 1259:

```python
    @mcp.tool(
        tags={"utility", "schema", "compatibility"},
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def kg_release_info(ctx: Context) -> KGReleaseInfoResponse:
        """Return the KG's release identity (`Schema_info` properties) and a compatibility verdict against this explorer-MCP version.

        **Call this first** in any new session — verifies the explorer's installed version satisfies the KG's declared `mcp_min_version`, and that the load-bearing schema shape (foundational labels, relationship types, `Schema_info` properties, non-zero gene/experiment counts) is present. The result is computed once at MCP server startup and cached; re-call is instant.

        Verdict semantics:
        - `ok`     — explorer satisfies KG min-version + all schema asserts pass.
        - `warn`   — at least one assert failed; tools still serve but may emit confusing errors against the affected shapes. Filter `asserts` on `passed=False` for the failure list.
        - `unknown` — could not evaluate (no `Schema_info` node in the KG — pre-2026-05-31 build, or wrong database).

        On non-`ok` verdicts, the tool emits `ctx.warning(summary)` so the surrounding MCP client surfaces it to the user. See `docs://guide/conventions` for cross-tool semantics.
        """
        await ctx.info("kg_release_info")
        try:
            report = _kg_compat_report(ctx)
            response = KGReleaseInfoResponse(**report)
            if response.verdict != "ok":
                await ctx.warning(response.summary)
            return response
        except Exception as e:
            await ctx.error(f"kg_release_info unexpected error: {e}")
            raise ToolError(f"Error in kg_release_info: {e}")
```

(The `await ctx.info("kg_release_info")` line mirrors `kg_schema`'s identical line at [tools.py:1268](multiomics_explorer/mcp_server/tools.py#L1268). Same `try/except → ToolError` pattern.)

- [ ] **Step 5: Update `EXPECTED_TOOLS` and rename the size-pinning test**

In `tests/unit/test_tool_wrappers.py`:

1. Find the `EXPECTED_TOOLS = [...]` list at line ~49. Add `"kg_release_info"` to it (preserve alphabetical / existing order — match the surrounding entries).

2. Find `test_expected_tools_size_unchanged_at_39` (around line 6418 per spec §10). Rename to `test_expected_tools_size_unchanged_at_40` and update the asserted count from `39` to `40`. Update the test's docstring if it mentions the number.

- [ ] **Step 6: Run tests to verify everything passes**

Run: `uv run pytest tests/unit/test_tool_wrappers.py -v 2>&1 | tail -25`
Expected: all previously-passing tests still green; the new `TestKGReleaseInfoTool` 4 tests pass; the renamed `test_expected_tools_size_unchanged_at_40` passes.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "mcp(tools): kg_release_info MCP tool + KGReleaseInfoResponse models"
```

---

## Task 6: Lifespan caches the report + MCP instructions update (Layer 3)

**Files:**
- Modify: `multiomics_explorer/mcp_server/server.py` (KGContext dataclass + lifespan + instructions string)

No new unit test — the integration test in Task 8 covers the lifespan path end-to-end. Bench-testing the lifespan in isolation requires too much mocking for too little signal.

- [ ] **Step 1: Extend `KGContext` and `lifespan`**

Open `multiomics_explorer/mcp_server/server.py`. Find the existing `KGContext` (around line 22) and the `lifespan` function (around line 27).

Update `KGContext` to add the cached report field:

```python
@dataclass
class KGContext:
    conn: GraphConnection
    kg_compat_report: dict  # api.kg_release_info shape, cached at lifespan startup
```

Update the lifespan to call `kg_release_info` after `verify_connectivity()`:

```python
@asynccontextmanager
async def lifespan(server: FastMCP):
    """Manage Neo4j connection lifecycle.

    Also runs the KG↔explorer compatibility check once at startup and
    caches the report on KGContext. The kg_release_info MCP tool reads
    from this cache. Per design spec
    docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md §9.
    """
    settings = get_settings()
    conn = GraphConnection(settings)
    if not conn.verify_connectivity():
        raise RuntimeError(f"Cannot connect to Neo4j at {settings.neo4j_uri}")
    logger.info("Connected to Neo4j at %s", settings.neo4j_uri)

    # KG compatibility check — defensive: never block startup on this.
    try:
        report = kg_release_info(conn)
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

Add the imports near the top of `server.py` (alongside the existing imports from the api/connection layers):

```python
from multiomics_explorer.api.functions import _get_explorer_version, kg_release_info
```

- [ ] **Step 2: Update the MCP `instructions` string**

Find the `instructions=(...)` block in the `FastMCP(...)` call (around line 42-64). Add the new "First call" hint near the top of the existing block, just after the opening tool-count line:

Original opening (excerpt):
```python
instructions=(
    "Multi-omics knowledge graph for Prochlorococcus and Alteromonas "
    "(39 tools across gene/sequence/expression/ortholog/ontology/cluster/"
    "chemistry/metabolomics/enrichment).\n\n"
    "Start here:\n"
```

Change to:
```python
instructions=(
    "Multi-omics knowledge graph for Prochlorococcus and Alteromonas "
    "(40 tools across gene/sequence/expression/ortholog/ontology/cluster/"
    "chemistry/metabolomics/enrichment).\n\n"
    "First call: kg_release_info — verifies your KG release matches what this "
    "explorer-MCP version expects. Surfaces the KG's identity (version, "
    "built_at, counts) and a verdict (ok / warn / unknown).\n\n"
    "Start here:\n"
```

(Two edits: bump `39 tools` → `40 tools`; insert the new paragraph.)

- [ ] **Step 3: Sanity-check the server still imports**

Run: `uv run python -c "from multiomics_explorer.mcp_server.server import mcp; print('ok, server module loads')"`
Expected: `ok, server module loads`

- [ ] **Step 4: Run the unit test suite (regression check)**

Run: `uv run pytest tests/unit/ -q 2>&1 | tail -5`
Expected: All previously-passing tests still pass (count should go up by the new tests added in Tasks 2/3/4/5).

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/mcp_server/server.py
git commit -m "mcp(server): cache kg_release_info on KGContext at lifespan startup"
```

---

## Task 7: Skill YAML + regenerated markdown (Layer 4)

**Files:**
- Create: `multiomics_explorer/inputs/tools/kg_release_info.yaml`
- Run: `scripts/build_about_content.py` (regenerates `multiomics_explorer/skills/multiomics-kg-guide/references/tools/kg_release_info.md`)

- [ ] **Step 1: Peek at an existing YAML for shape**

Run: `cat multiomics_explorer/inputs/tools/kg_schema.yaml`

(kg_schema is the closest analog — short, no-args, KG-introspection. Use its shape.)

- [ ] **Step 2: Create the YAML**

Create `multiomics_explorer/inputs/tools/kg_release_info.yaml` with the following content (adjust field names if Step 1 shows the existing YAMLs use a different key structure — `examples` / `mistakes` / `chaining` / `verbose_fields` are the standard sections per `CLAUDE.md`):

```yaml
examples:
  - title: "First call in a new session"
    description: |
      Run kg_release_info before any other tool to verify the KG you're
      connected to is compatible with this explorer-MCP version. The
      result is cached at server startup; calling this tool repeatedly
      is free.
    call: |
      kg_release_info()
    response_shape: |
      {
        "verdict": "ok",
        "explorer_version": "0.1.0a1",
        "kg": {"version": "0.1.0-alpha.1", "gene_count": 120416, ...},
        "asserts": [...16 entries...],
        "summary": "OK: explorer 0.1.0a1 satisfies KG mcp_min_version 0.1.0; 16/16 schema asserts pass."
      }

  - title: "Diagnose a 'warn' verdict"
    description: |
      When verdict is 'warn', inspect the `asserts` list and filter for
      `passed=False`. Each failed assert carries a `detail` string
      explaining what was missing. Common causes:
        - The KG was upgraded but you're still running an older explorer
          (the version_compat assert fails).
        - You connected to a non-KG Neo4j database (most node-label
          asserts fail).
    call: |
      report = kg_release_info()
      failures = [a for a in report.asserts if not a.passed]

mistakes:
  - title: "Don't call kg_release_info on every tool invocation"
    description: |
      The check runs ONCE at MCP server startup. The tool reads from a
      cached result — calling it 100 times returns the same answer 100
      times. Once per session is enough.

  - title: "Don't expect schema-shape divergence to surface here for ontology-specific labels"
    description: |
      EXPECTED_KG_SHAPE only asserts the load-bearing core (Gene,
      Experiment, OrthologGroup, Publication, Schema_info). Ontology
      labels (KeggTerm, EcTerm, TcdbFamily, etc.) are NOT asserted —
      they fail-gracefully at query time in their respective tools. If
      verdict='ok' but a specific ontology tool errors, the issue is
      tool-side, not compat-check-side.

chaining:
  - title: "Verify compat → introspect schema → run real tools"
    description: |
      Standard opening sequence:
        1. kg_release_info()        — verdict + KG identity
        2. kg_schema()              — full label/property listing
        3. (real tools)             — your actual analysis
      If verdict != 'ok', stop and surface the warning to the user
      before running real analysis.
```

- [ ] **Step 3: Regenerate the skill markdown**

Run: `uv run python scripts/build_about_content.py`
Expected: Writes `multiomics_explorer/skills/multiomics-kg-guide/references/tools/kg_release_info.md` and updates the per-tool registry.

- [ ] **Step 4: Lint the new tool's about-content**

Run: `uv run python scripts/build_about_content.py --lint kg_release_info`
Expected: No errors.

- [ ] **Step 5: Run the about-content tests**

Run: `uv run pytest tests/unit/test_about_content.py -q 2>&1 | tail -5`
Expected: All tests pass (the YAML / schema / MD round-trip is consistent).

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/inputs/tools/kg_release_info.yaml multiomics_explorer/skills/multiomics-kg-guide/references/tools/kg_release_info.md
git commit -m "skill(kg_release_info): YAML inputs + regenerated tool reference MD"
```

---

## Task 8: Integration tests — drift + live KG + MCP smoke

**Files:**
- Modify: `tests/integration/test_kg_constants_drift.py` (add `EXPECTED_KG_SHAPE` drift test)
- Modify: `tests/integration/test_api_contract.py` (add live-KG test for `kg_release_info`)
- Modify: `tests/integration/test_mcp_tools.py` (add MCP smoke test via FastMCP test client)

All three sit behind `pytest.mark.kg` — require the live Neo4j at `bolt://localhost:7687`.

- [ ] **Step 1: Peek at existing integration patterns**

Run: `head -60 tests/integration/test_api_contract.py`
Run: `head -60 tests/integration/test_mcp_tools.py`

Note the fixtures (typically a session-scoped `conn` or `mcp_client`) and reuse them. Don't invent new fixtures.

- [ ] **Step 2: Add the drift test**

Append to `tests/integration/test_kg_constants_drift.py` (the file is already `pytestmark = pytest.mark.kg`):

```python


from multiomics_explorer.kg.constants import EXPECTED_KG_SHAPE


def test_expected_kg_shape_labels_present_in_kg(conn):
    """Every node label in EXPECTED_KG_SHAPE['required_node_labels']
    must exist in the live KG. Drift catches: KG renamed a label, KG
    dropped a label we expected.

    Failure remediation: update EXPECTED_KG_SHAPE in kg/constants.py
    (drop the dead label, or add the renamed one)."""
    rows = conn.execute_query("CALL db.labels() YIELD label RETURN collect(label) AS labels")
    live_labels = set(rows[0]["labels"])
    expected = set(EXPECTED_KG_SHAPE["required_node_labels"])
    missing = expected - live_labels
    assert not missing, _drift_msg(
        "EXPECTED_KG_SHAPE['required_node_labels']",
        "kg/constants.py",
        live_labels, expected,
    )


def test_expected_kg_shape_relationship_types_present_in_kg(conn):
    """Every relationship type in EXPECTED_KG_SHAPE must exist."""
    rows = conn.execute_query(
        "CALL db.relationshipTypes() YIELD relationshipType "
        "RETURN collect(relationshipType) AS rt"
    )
    live_rts = set(rows[0]["rt"])
    expected = set(EXPECTED_KG_SHAPE["required_relationship_types"])
    missing = expected - live_rts
    assert not missing, _drift_msg(
        "EXPECTED_KG_SHAPE['required_relationship_types']",
        "kg/constants.py",
        live_rts, expected,
    )


def test_expected_kg_shape_schema_info_props_present_in_kg(conn):
    """Every property in EXPECTED_KG_SHAPE['schema_info_required_props']
    must exist as a non-null Schema_info property in the live KG."""
    rows = conn.execute_query(
        "MATCH (s:Schema_info {id: 'schema_info'}) RETURN s { .* } AS si"
    )
    assert rows, "Schema_info node not found — KG predates 2026-05-31?"
    si = rows[0]["si"]
    expected = set(EXPECTED_KG_SHAPE["schema_info_required_props"])
    missing = {p for p in expected if si.get(p) is None}
    assert not missing, (
        f"EXPECTED_KG_SHAPE['schema_info_required_props'] in kg/constants.py "
        f"is out of sync with the live KG.\n  Missing or null on Schema_info: {missing}\n"
        f"  Update kg/constants.py to drop the dead props, or rebuild the KG."
    )
```

(If the existing tests use a different fixture name than `conn`, adjust accordingly — the head-of-file peek in Step 1 will show.)

- [ ] **Step 3: Add the live-KG api test**

Append to `tests/integration/test_api_contract.py`:

```python


class TestKGReleaseInfoLive:
    """Live-KG smoke for api/functions.kg_release_info."""

    pytestmark = pytest.mark.kg

    def test_returns_ok_verdict_against_dev_kg(self, conn):
        """The dev KG at localhost:7687 should always satisfy the
        installed explorer's compatibility check. If this fails,
        EITHER:
          1. The dev KG floated past the explorer's installed version
             (run /release-explorer to bump explorer).
          2. EXPECTED_KG_SHAPE drifted from the dev KG schema
             (the drift tests in test_kg_constants_drift.py will tell
             you which assert failed).
        """
        from multiomics_explorer import kg_release_info

        report = kg_release_info(conn)

        if report["verdict"] != "ok":
            pytest.fail(
                f"Expected verdict='ok' against dev KG; got "
                f"verdict={report['verdict']!r}, summary={report['summary']!r}.\n"
                f"Failed asserts: "
                f"{[a['name'] for a in report['asserts'] if not a['passed']]}"
            )

    def test_explorer_version_matches_importlib(self, conn):
        """The reported explorer_version mirrors importlib.metadata exactly."""
        from importlib.metadata import version
        from multiomics_explorer import kg_release_info

        report = kg_release_info(conn)
        assert report["explorer_version"] == version("multiomics-explorer")

    def test_kg_identity_has_real_counts(self, conn):
        """The KG identity carries plausible counts (catches 'connected to empty DB')."""
        from multiomics_explorer import kg_release_info

        report = kg_release_info(conn)
        assert report["kg"]["gene_count"] > 0
        assert report["kg"]["experiment_count"] > 0
        assert report["kg"]["version"]  # any non-empty string
```

(Add the `import pytest` at top-of-file if not already present.)

- [ ] **Step 4: Add the MCP smoke test**

Find the existing pattern in `tests/integration/test_mcp_tools.py` for invoking a tool via the FastMCP test client (e.g., `kg_schema` is the closest analog). Add a test alongside it:

```python


class TestKGReleaseInfoMCPSmoke:
    """Live-KG smoke through the MCP layer (lifespan + tool call)."""

    pytestmark = pytest.mark.kg

    async def test_tool_returns_ok_verdict(self, mcp_client):
        """Mirror the api-layer test through the MCP wrapper. Exercises
        the full lifespan path: server boot → kg_release_info(conn) →
        cached on KGContext → tool reads from cache."""
        result = await mcp_client.call_tool("kg_release_info", {})

        # Tool returns a structured response — pull the verdict out of it.
        # Exact extraction depends on FastMCP's test-client envelope; see
        # the analogous kg_schema test in this file for the pattern.
        payload = result.structured_content if hasattr(result, "structured_content") else result
        assert payload["verdict"] == "ok", (
            f"verdict={payload['verdict']!r}, summary={payload['summary']!r}"
        )
        assert payload["explorer_version"]
        assert payload["kg"]["version"]
```

(If `mcp_client` is not the existing fixture name, follow whatever the file's conventions are — the analogous `kg_schema` test will show the right shape. `call_tool("kg_schema", {})` returning a `result` with a `structured_content` attribute is the FastMCP 3.x pattern.)

- [ ] **Step 5: Run the integration suite**

Run: `uv run pytest -m kg -v -k "kg_release_info or kg_shape or kg_constants_drift" 2>&1 | tail -30`
Expected: All `kg_release_info` / `EXPECTED_KG_SHAPE` related tests pass. (If you see `verdict='warn'` because the dev KG declares `mcp_min_version=0.1.0` and the installed explorer is `0.1.0a1`, that's exactly the pre-release coordination case the spec flagged — see CHANGELOG cross-repo coordination note. Either bump the dev KG's `mcp_min_version` to `0.1.0-alpha.1`, or bump the installed explorer to bare `0.1.0`, before merging. Surface this finding to the user; do NOT silently work around it.)

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_kg_constants_drift.py tests/integration/test_api_contract.py tests/integration/test_mcp_tools.py
git commit -m "test(integration): kg_release_info live-KG + drift + MCP smoke"
```

---

## Task 9: CHANGELOG + final verification

**Files:**
- Modify: `CHANGELOG.md` (add `[Unreleased]` entry)

- [ ] **Step 1: Update CHANGELOG `[Unreleased]`**

Edit `CHANGELOG.md`. Under `## [Unreleased]` → `### Added`, add:

```
- `kg_release_info` MCP tool: returns the KG's release identity
  (`Schema_info` properties — version, built_at, counts, git identity)
  and a three-valued compatibility verdict (`ok` / `warn` / `unknown`)
  against the installed explorer version. Run by the MCP server lifespan
  at startup; cached on `KGContext`; tool reads from cache. PEP 440
  semver comparison via `packaging.version.Version` (catches the
  pre-release-vs-release coordination case). 16 asserts in the v1
  EXPECTED_KG_SHAPE check (5 Schema_info properties + 5 node labels +
  3 relationship types + 2 non-zero counts + 1 version compat). See
  `docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md`.
- MCP server `instructions` updated to point agents at `kg_release_info`
  as a first call in any new session.
```

- [ ] **Step 2: Full test suite**

Run: `uv run pytest tests/unit/ -q 2>&1 | tail -5`
Expected: All unit tests pass.

Run: `uv run pytest -m kg -q 2>&1 | tail -10`
Expected: All KG-marked integration tests pass (assuming a running Neo4j on `localhost:7687`).

- [ ] **Step 3: Ruff lint**

Run: `uv run ruff check multiomics_explorer/ 2>&1 | tail -10`
Expected: No new errors introduced. (Pre-existing errors in `enrichment.py`, `queries_lib.py`, `mcp_server/server.py` are baseline and unrelated.)

- [ ] **Step 4: Manual smoke — start the MCP, observe the INFO log line**

Run: `uv run multiomics-kg-mcp 2>&1 &` then `sleep 2; jobs; kill %1`
Expected: Stderr shows one INFO line like:
`KG compat: OK: explorer <version> satisfies KG mcp_min_version <version>; 16/16 schema asserts pass.`

If the message is `WARN:` or `UNKNOWN:`, investigate before merging.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): record kg_release_info compat-check feature under [Unreleased]"
```

- [ ] **Step 6: Final state**

```bash
git log --oneline -10
git status --short
```

Expected: Nine new commits on top of the prior release-infra commit (`5ef0e13`). Working tree clean except `.claude/scheduled_tasks.lock` (harness file).

---

## Notes for the implementer

- **TDD throughout.** Each task that adds behavior follows write-failing-test → run → implement → run → commit. The constant-only task (Task 1) and the YAML/lifespan tasks (Tasks 6, 7) have no isolated unit test — they're covered transitively by the integration tests in Task 8.
- **Layer boundaries are load-bearing.** See `.claude/skills/layer-rules`. Don't shortcut: e.g., don't put version-comparison logic in `kg/` (it'd execute in Layer 1, against the rules), and don't compute response fields in `mcp_server/` (api/ owns that).
- **The pre-release coordination edge case** (`0.1.0a1` vs bare `0.1.0`) is *the* case this feature exists to catch. The dedicated unit test in Task 3 + the warning-when-it-bites behavior in Task 8 Step 5 are the two halves. Don't paper over Task 8 Step 5 if it fires — the failing test means the contract divergence is real and needs cross-repo coordination per KG plan §2.3.
- **No new runtime deps.** `packaging` is already transitive via pydantic. Verified in this venv (`uv run python -c "from packaging.version import Version"` succeeds).
