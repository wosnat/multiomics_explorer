# kg_schema

## What it does

Live-KG schema: node labels with property names and types, relationship types with source and target labels.

Use before writing a `run_cypher` query; for filter values use `list_filter_values`, for the entity model docs://guide/concepts.
Filters: labels, relationship_types, section.
Returns: nodes, relationships, not_found_labels, not_found_relationship_types; no row list — scope the call or it dumps the whole graph.
docs://tools/kg_schema.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| labels | list[string] \| None | None | Restrict the node section to these labels (e.g. ['Gene', 'Experiment']). Omit for every label. Unknown values land in `not_found_labels`, not an error. |
| relationship_types | list[string] \| None | None | Restrict the relationship section to these types (e.g. ['Changes_expression_of']). Omit for every type. Unknown values land in `not_found_relationship_types`, not an error. |
| section | string ('nodes', 'relationships', 'both') | both | Which half of the schema to return. 'both' (default) returns both node and relationship sections; 'nodes' / 'relationships' returns only that section (the other comes back as an empty dict). |

## Example

### Scope the node section to one label's properties

```python
kg_schema(labels=['Gene'], section='nodes')
```

## Response sketch

```expected-keys
nodes, relationships, not_found_labels, not_found_relationship_types
```

## Common mistakes

- Calling kg_schema() with no arguments dumps every node label and relationship type in the KG (100+ KB) — pass labels / relationship_types / section to scope the call to what you actually need before validating a run_cypher query.

- Schema does not include node counts — use run_cypher for counts (or kg_release_info for the headline gene / organism / experiment / paper counts)

- This is the one tool whose result is not a list envelope: no total_matching / results, just {nodes, relationships} keyed by label / relationship type. Ontology memberships are relationships (Gene_has_tcdb_family, Gene_involved_in_biological_process, ...), never Gene properties.

## Chaining patterns

- kg_schema → run_cypher

Full reference (all examples, full response format, verbose fields): `docs://tools/kg_schema/full`
