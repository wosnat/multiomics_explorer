"""Graph schema introspection from the live Neo4j instance."""

from dataclasses import dataclass, field
from typing import Any

from multiomics_explorer.kg.connection import GraphConnection


@dataclass
class NodeSchema:
    """Schema for a single node label."""
    label: str
    count: int = 0
    properties: dict[str, str] = field(default_factory=dict)  # name -> type string


@dataclass
class RelationshipSchema:
    """Schema for a single relationship type."""
    type: str
    source_labels: list[str] = field(default_factory=list)
    target_labels: list[str] = field(default_factory=list)
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class GraphSchema:
    """Complete graph schema introspected from Neo4j."""
    nodes: dict[str, NodeSchema] = field(default_factory=dict)
    relationships: dict[str, RelationshipSchema] = field(default_factory=dict)

    def to_prompt_string(self) -> str:
        """Format schema for injection into LLM prompts."""
        lines = ["## Graph Schema\n", "### Node Types\n"]

        for label, node in sorted(self.nodes.items()):
            props = ", ".join(f"{k}: {v}" for k, v in sorted(node.properties.items()))
            lines.append(f"- **{label}** ({node.count} nodes)")
            if props:
                lines.append(f"  Properties: {props}")

        lines.append("\n### Relationship Types\n")
        for rel_type, rel in sorted(self.relationships.items()):
            sources = ", ".join(rel.source_labels) or "?"
            targets = ", ".join(rel.target_labels) or "?"
            lines.append(f"- **{rel_type}**: ({sources}) -> ({targets})")
            if rel.properties:
                props = ", ".join(f"{k}: {v}" for k, v in sorted(rel.properties.items()))
                lines.append(f"  Properties: {props}")

        return "\n".join(lines)


def _infer_type(value: Any) -> str:
    """Infer a simple type string from a Neo4j value."""
    if value is None:
        return "any"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    return "string"


def load_schema_from_neo4j(conn: GraphConnection) -> GraphSchema:
    """Introspect the full graph schema from a live Neo4j instance.

    Queries node labels, relationship types, and samples properties
    from each to build a GraphSchema object.
    """
    schema = GraphSchema()

    # Node labels and counts
    labels = conn.get_labels()
    for label in labels:
        count = conn.get_node_count(label)
        node_schema = NodeSchema(label=label, count=count)

        # Sample one node to get property names and types
        sample = conn.execute_query(
            f"MATCH (n:`{label}`) RETURN properties(n) AS props LIMIT 1"
        )
        if sample and sample[0]["props"]:
            for k, v in sample[0]["props"].items():
                node_schema.properties[k] = _infer_type(v)

        schema.nodes[label] = node_schema

    # Relationship types with source/target labels and properties
    rel_types = conn.get_relationship_types()
    for rel_type in rel_types:
        rel_schema = RelationshipSchema(type=rel_type)

        # Get source and target labels
        endpoints = conn.execute_query(
            f"MATCH (a)-[r:`{rel_type}`]->(b) "
            f"RETURN DISTINCT labels(a) AS src, labels(b) AS tgt LIMIT 10"
        )
        src_labels = set()
        tgt_labels = set()
        for row in endpoints:
            src_labels.update(row["src"])
            tgt_labels.update(row["tgt"])
        rel_schema.source_labels = sorted(src_labels)
        rel_schema.target_labels = sorted(tgt_labels)

        # Sample one relationship to get properties
        sample = conn.execute_query(
            f"MATCH ()-[r:`{rel_type}`]->() RETURN properties(r) AS props LIMIT 1"
        )
        if sample and sample[0]["props"]:
            for k, v in sample[0]["props"].items():
                rel_schema.properties[k] = _infer_type(v)

        schema.relationships[rel_type] = rel_schema

    return schema
