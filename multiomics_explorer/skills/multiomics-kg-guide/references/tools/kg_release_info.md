# kg_release_info

## What it does

KG release identity (Schema_info version, built_at, node counts) plus a compatibility verdict against this explorer build.

Use as the first call of a session; for the graph shape use `kg_schema`, for live vocabulary values `list_filter_values`.
Filters: none.
Returns: verdict, explorer_version, kg, asserts, summary; no row list. `warn` means quoted value lists may be stale, never that calls fail.
docs://tools/kg_release_info.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|

## Example

### First call in a new session

```python
kg_release_info()
```

## Response sketch

```expected-keys
verdict, explorer_version, kg, asserts, summary
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

## Chaining patterns

- kg_release_info → kg_schema (verify compat, then introspect schema)
- kg_release_info → any analysis tool (if verdict != 'ok', surface warning before running real analysis)
- kg_release_info (controlled_vocabularies_hash assert failed) → list_filter_values(filter_type=...) for the live value set instead of any quoted list

Full reference (all examples, full response format, verbose fields): `docs://tools/kg_release_info/full`
