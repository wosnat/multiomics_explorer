# kg_schema

## What it does

Get the knowledge graph schema: node labels with property names/types,
and relationship types with source/target labels.

Use this before run_cypher to understand what labels and properties are queryable.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|

## Response format

### Envelope

```expected-keys
nodes, relationships
```

- **nodes** (object): Node labels mapped to their property definitions. Each value is {'properties': {'prop_name': 'type_string', ...}}.
- **relationships** (object): Relationship types mapped to their definitions. Each value is {'source_labels': [...], 'target_labels': [...], 'properties': {'prop_name': 'type_string', ...}}.

## Few-shot examples

### Example 1: Get the full schema

```example-call
kg_schema()
```

```example-response
{"nodes": {"Gene": {"properties": {"locus_tag": "STRING", "gene_name": "STRING", ...}}, "GOTerm": {"properties": {"id": "STRING", "name": "STRING", ...}}, ...}, "relationships": {"Has_function": {"source_labels": ["Gene"], "target_labels": ["GOTerm"], "properties": {}}, ...}}
```

## Chaining patterns

```
kg_schema → run_cypher
```

## Common mistakes

- Schema does not include node counts — use run_cypher for counts

```mistake
kg_schema() to discover valid organism or category filter values
```

```correction
list_filter_values() for categorical filter options; list_organisms() for organism details
```

## Package import equivalent

```python
from multiomics_explorer import kg_schema

result = kg_schema()
# returns dict with keys: nodes, relationships
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
