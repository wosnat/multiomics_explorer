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

- Calling kg_schema() with no arguments dumps every node label and relationship type in the KG (~35 KB, ~9k tokens) — pass labels / relationship_types / section to scope the call to what you actually need before validating a run_cypher query.

- BioCypher parent labels (NamedThing, Entity, BiologicalEntity, GeneOntology, ...) sit on many node types and are listed with no properties, and relationship source_labels / target_labels name only the concrete labels — MATCH on the concrete label (Gene, TcdbFamily, ...).

- Schema does not include node counts — use run_cypher for counts (or kg_release_info for the headline gene / organism / experiment / paper counts)

## Chaining patterns

- kg_schema → run_cypher
- kg_schema(relationship_types=['Biological_process_transports_metabolite', ...]) → run_cypher over Gene → GO term → Metabolite (examples: docs://analysis/transport)

Full reference (all examples, full response format, verbose fields): `docs://tools/kg_schema/full`
