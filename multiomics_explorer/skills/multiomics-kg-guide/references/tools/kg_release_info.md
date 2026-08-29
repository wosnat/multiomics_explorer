# kg_release_info

## What it does

Return the KG's release identity (`Schema_info` properties) and a compatibility verdict against this explorer-MCP version.

**Call this first** in any new session — verifies the explorer's installed version satisfies the KG's declared `mcp_min_version`, and that the load-bearing schema shape (foundational labels, relationship types, `Schema_info` properties, non-zero gene/experiment counts) is present. The result is computed once at MCP server startup and cached; re-call is instant.

Verdict semantics:
- `ok`     — explorer satisfies KG min-version + all schema asserts pass.
- `warn`   — at least one assert failed; tools still serve but may emit confusing errors against the affected shapes. Filter `asserts` on `passed=False` for the failure list.
- A failed `controlled_vocabularies_hash` assert (bucket 6) yields `warn`: filters still validate live and `list_filter_values` reads live, but docs://ontologies/{key} pages (index: docs://ontologies/index) and parameter descriptions may list stale values. `kg.controlled_vocabularies_hash` carries the live digest.
- `unknown` — could not evaluate (no `Schema_info` node in the KG — legacy build without release metadata, or wrong database).

On non-`ok` verdicts, the tool emits `ctx.warning(summary)` so the surrounding MCP client surfaces it to the user. See `docs://guide/conventions` for cross-tool semantics.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|

## Response format

### Envelope

```expected-keys
verdict, explorer_version, kg, asserts, summary
```

- **verdict** (string ('ok', 'warn', 'unknown')): 'ok' = explorer version satisfies KG.mcp_min_version AND all schema asserts pass. 'warn' = at least one assert failed; tools still work but may emit confusing errors. 'unknown' = check could not be evaluated (Schema_info missing — legacy KG build without release metadata, or wrong DB).
- **explorer_version** (string): Installed multiomics-explorer version (PEP 440 form, e.g. '0.1.0a1').
- **kg** (KGIdentity): The KG's self-declared release identity.
- **asserts** (list[KGAssert]): Every assertion evaluated, pass + fail. Filter `passed=False` for the failure list.
- **summary** (string): One-line human-readable verdict.

### Assert kinds

Each `asserts[]` entry belongs to one of six families (`kind`):
`schema_info_prop` — the named `Schema_info` property is present and
non-null on the live KG; `node_label` — the named node label exists
in `db.labels()`; `relationship_type` — the named relationship type
exists in `db.relationshipTypes()`; `nonzero_count` — the named
`Schema_info` count property is a positive int; `version_compat` —
the installed explorer version satisfies `KG.mcp_min_version` under
PEP 440; `controlled_vocabularies_hash` — the live
`Schema_info.controlled_vocabularies_hash` equals the hash this
explorer was built against (a miss yields `warn`, never worse).


## Few-shot examples

### Example 1: First call in a new session (illustrative — not a live response)

```example-call
kg_release_info()
```

*Version strings, hashes and counts below are placeholders for the shape — every field is read live from Schema_info and changes with each KG / explorer release.*

```example-response
{"verdict": "ok", "explorer_version": "0.1.0a5", "kg": {"version": "0.1.0-alpha.7", "mcp_min_version": "0.1.0a5", "deployment_role": "local-dev", "controlled_vocabularies_hash": "sha256:6170...e0ae", "gene_count": 127458, "organism_count": 48, "experiment_count": 209, "paper_count": 49}, "asserts": [{"name": "node_label:Gene", "kind": "node_label", "passed": true, "detail": null}, "...15 more entries...", {"name": "controlled_vocabularies_hash", "kind": "controlled_vocabularies_hash", "passed": true, "expected": "sha256:6170...e0ae", "actual": "sha256:6170...e0ae", "detail": null}], "summary": "OK: explorer 0.1.0a5 satisfies KG mcp_min_version 0.1.0a5; 17/17 schema asserts pass."}

# kg.deployment_role is the KG's self-declared environment ('local-dev' |
# 'staging' | 'production'), stamped at build time. null on legacy KGs
# built before the property existed — treat null as unknown. The explorer
# reads this verbatim rather than inferring dev-vs-prod from host/port.
```

### Example 2: Vocabulary set differs from the pinned one (sixth assert fails, verdict warn) (illustrative — not a live response)

```example-call
kg_release_info()
```

*A warn verdict cannot be reproduced against a matching KG — this shows the shape you get after a KG rebuild changes the vocabulary set.*

```example-response
# The KG stamps Schema_info.controlled_vocabularies_hash — a sha256 over
# every ControlledVocabulary entry's {id, value_type, closed, values,
# sparse, expected_empty, exhaustive, min_value, max_value,
# signal_count, signals}. `description` is excluded, so doc-only
# vocabulary edits do not change it. The explorer pins the hash of the
# KG it was built against; the sixth assert bucket compares the two.
{"verdict": "warn", "kg": {"controlled_vocabularies_hash": "sha256:e81d...efd4", "...": "..."}, "asserts": ["...16 schema asserts, all passed...", {"name": "controlled_vocabularies_hash", "kind": "controlled_vocabularies_hash", "passed": false, "expected": "sha256:6170...e0ae", "actual": "sha256:e81d...efd4", "detail": "Schema_info.controlled_vocabularies_hash is sha256:e81d...efd4, explorer was built against sha256:6170...e0ae."}], "summary": "WARN: ... Vocabulary set differs from the one this explorer was built against — filters still validate live and list_filter_values reads live, but docs://ontologies/{key} pages and parameter descriptions may list stale values."}

# What this warn means in practice: nothing is broken. Every filter
# value is validated against the live KG at call time and
# list_filter_values reads the live ControlledVocabulary nodes, so
# calls keep working. What may be stale is the DOCUMENTATION — the
# value lists quoted in docs://ontologies/{key} pages and in parameter
# descriptions were rendered from the pinned vocabulary. When in doubt,
# trust list_filter_values(filter_type=...) over any quoted list.
# A KG built before the vocabulary contract has no hash at all; that
# also fails this bucket (detail "KG predates the vocabulary contract")
# and is likewise only a warn.
```

### Example 3: Diagnose a warn verdict

```
Step 1: kg_release_info()
        → check verdict field; if "warn", inspect the asserts list

Step 2: filter for failed asserts
        failures = [a for a in report["asserts"] if not a["passed"]]

Step 3: read each failure's detail string
        Common causes: KG upgraded but explorer is older (version_compat fails);
        connected to a non-KG Neo4j database (most node-label asserts fail);
        KG rebuilt with a changed vocabulary set (controlled_vocabularies_hash
        fails — docs may quote stale values, calls are unaffected).
```

## Chaining patterns

```
kg_release_info → kg_schema (verify compat, then introspect schema)
kg_release_info → any analysis tool (if verdict != 'ok', surface warning before running real analysis)
kg_release_info (controlled_vocabularies_hash assert failed) → list_filter_values(filter_type=...) for the live value set instead of any quoted list
```

## Common mistakes

```mistake
Calling kg_release_info on every tool invocation
```

```correction
The check runs once at MCP server startup and caches the result. One call per session is enough — calling it 100 times returns the same answer 100 times.
```

```mistake
Expecting kg_release_info to catch ontology-label mismatches (KeggTerm, EcTerm, TcdbFamily, etc.)
```

```correction
EXPECTED_KG_SHAPE only asserts the load-bearing core labels (Gene, Experiment, OrthologGroup, Publication, Schema_info). Ontology-specific labels are not asserted — they fail gracefully at query time. If verdict='ok' but a specific ontology tool errors, the issue is tool-side, not compat-check-side.
```

```mistake
Treating a failed controlled_vocabularies_hash assert as a broken KG and refusing to run analyses
```

```correction
It is a warn, never worse. The hash covers the vocabulary VALUE SETS (ids, values, closed/sparse flags, score signals) — not descriptions. A mismatch means the docs://ontologies/{key} pages and parameter descriptions may list stale values; filters still validate live and list_filter_values reads live. Keep working; prefer list_filter_values over any quoted value list.
```

```mistake
Expecting the pinned hash to follow a KG rebuild
```

```correction
The pin lives in the explorer (EXPECTED_KG_SHAPE) and is set at explorer release time to equal the live KG's hash at cut time — that equality is a release-time rule. A dev KG build that adds a vocabulary value (e.g. a new treatment_type) fails this bucket until the next explorer release re-pins it; expected during development.
```

- `kg.controlled_vocabularies_hash` is passed through from Schema_info like every other identity field; it is null on KGs built before the vocabulary contract existed, and the sixth assert then fails with detail 'KG predates the vocabulary contract' (still a warn).

## Package import equivalent

```python
from multiomics_explorer import kg_release_info

result = kg_release_info()
# returns dict with keys: verdict, explorer_version, kg, asserts, summary
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
