# kg_release_info

## What it does

Return the KG's release identity (`Schema_info` properties) and a compatibility verdict against this explorer-MCP version.

**Call this first** in any new session — verifies the explorer's installed version satisfies the KG's declared `mcp_min_version`, and that the load-bearing schema shape (foundational labels, relationship types, `Schema_info` properties, non-zero gene/experiment counts) is present. The result is computed once at MCP server startup and cached; re-call is instant.

Verdict semantics:
- `ok`     — explorer satisfies KG min-version + all schema asserts pass.
- `warn`   — at least one assert failed; tools still serve but may emit confusing errors against the affected shapes. Filter `asserts` on `passed=False` for the failure list.
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

## Few-shot examples

### Example 1: First call in a new session

```example-call
kg_release_info()
```

```example-response
{"verdict": "ok", "explorer_version": "0.1.0a1", "kg": {"version": "0.1.0-alpha.1", "mcp_min_version": "0.1.0a1", "deployment_role": "local-dev", "gene_count": 120416, "organism_count": 45, "experiment_count": 312}, "asserts": [{"name": "node_label:Gene", "kind": "node_label", "passed": true, "detail": null}, "...15 more entries..."], "summary": "OK: explorer 0.1.0a1 satisfies KG mcp_min_version 0.1.0a1; 16/16 schema asserts pass."}

# kg.deployment_role is the KG's self-declared environment ('local-dev' |
# 'staging' | 'production'), stamped at build time. null on legacy KGs
# built before the property existed — treat null as unknown. The explorer
# reads this verbatim rather than inferring dev-vs-prod from host/port.
```

### Example 2: Diagnose a warn verdict

```
Step 1: kg_release_info()
        → check verdict field; if "warn", inspect the asserts list

Step 2: filter for failed asserts
        failures = [a for a in report["asserts"] if not a["passed"]]

Step 3: read each failure's detail string
        Common causes: KG upgraded but explorer is older (version_compat fails);
        connected to a non-KG Neo4j database (most node-label asserts fail).
```

## Chaining patterns

```
kg_release_info → kg_schema (verify compat, then introspect schema)
kg_release_info → any analysis tool (if verdict != 'ok', surface warning before running real analysis)
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

## Package import equivalent

```python
from multiomics_explorer import kg_release_info

result = kg_release_info()
# returns dict with keys: verdict, explorer_version, kg, asserts, summary
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
