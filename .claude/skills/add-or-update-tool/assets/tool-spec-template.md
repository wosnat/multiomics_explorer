# Tool spec: {tool-name}

## Purpose

What the tool does and why it's needed.

## Use cases

- Who calls this tool and in what context
- What chains it participates in (what tool comes before/after)
- Chat mode vs agentic mode usage

## KG dependencies

Nodes, edges, and properties this tool queries.
Link to KG spec if schema changes were needed: `docs/kg-specs/{tool-name}.md`

## Parameters

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| — | — | — | — | — |

## Summary mode

| Field | Type | Description |
|---|---|---|
| total | int | Total matching results |
| — | — | — |

What dimensions to break down by:
-
What availability signals to include:
-

## Detail mode

### Return fields

| Field | Type | Description |
|---|---|---|
| — | — | — |

### Sort key

What field to sort by, and direction (e.g., `score DESC, locus_tag ASC`).

### Default limit

Default: —, Max: —

### Truncation metadata

`total`, `returned`, `truncated` — standard or custom?

## Special handling

- Caching: yes/no, what to cache
- Multi-query orchestration: does the API function make multiple builder calls?
- Lucene retry: does this tool use fulltext search?
- Grouping: group results by organism or other dimension?

## Status

- [ ] Scope reviewed with user
- [ ] KG spec complete (if needed)
- [ ] KG changes landed (if needed)
- [ ] Mode design reviewed with user
- [ ] Ready for Phase 2 (build)
