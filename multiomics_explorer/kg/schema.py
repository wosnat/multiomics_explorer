"""Graph schema introspection from the live Neo4j instance."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from multiomics_explorer.kg.connection import GraphConnection

BASELINE_PATH = Path(__file__).parent.parent / "config" / "schema_baseline.yaml"


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

    def to_dict(self) -> dict:
        """Serialize to a plain dict (suitable for YAML/JSON)."""
        return {
            "nodes": {
                label: {
                    "properties": dict(sorted(n.properties.items())),
                }
                for label, n in sorted(self.nodes.items())
            },
            "relationships": {
                rt: {
                    "source_labels": r.source_labels,
                    "target_labels": r.target_labels,
                    "properties": dict(sorted(r.properties.items())),
                }
                for rt, r in sorted(self.relationships.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphSchema":
        """Deserialize from a plain dict."""
        schema = cls()
        for label, info in data.get("nodes", {}).items():
            schema.nodes[label] = NodeSchema(
                label=label,
                properties=info.get("properties", {}),
            )
        for rt, info in data.get("relationships", {}).items():
            schema.relationships[rt] = RelationshipSchema(
                type=rt,
                source_labels=info.get("source_labels", []),
                target_labels=info.get("target_labels", []),
                properties=info.get("properties", {}),
            )
        return schema

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

        # Sample multiple nodes to capture optional properties
        sample = conn.execute_query(
            f"MATCH (n:`{label}`) RETURN properties(n) AS props LIMIT 10"
        )
        for row in sample:
            if row["props"]:
                for k, v in row["props"].items():
                    if k not in node_schema.properties or node_schema.properties[k] == "any":
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

        # Sample multiple relationships to capture optional properties
        sample = conn.execute_query(
            f"MATCH ()-[r:`{rel_type}`]->() RETURN properties(r) AS props LIMIT 10"
        )
        for row in sample:
            if row["props"]:
                for k, v in row["props"].items():
                    if k not in rel_schema.properties or rel_schema.properties[k] == "any":
                        rel_schema.properties[k] = _infer_type(v)

        schema.relationships[rel_type] = rel_schema

    return schema


def save_baseline(schema: GraphSchema, path: Path = BASELINE_PATH) -> Path:
    """Save a schema snapshot as the baseline YAML file."""
    data = {
        "version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "schema": schema.to_dict(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return path


def load_baseline(path: Path = BASELINE_PATH) -> tuple[GraphSchema, dict]:
    """Load baseline schema from YAML. Returns (schema, metadata)."""
    data = yaml.safe_load(path.read_text())
    schema = GraphSchema.from_dict(data["schema"])
    return schema, {"version": data.get("version"), "captured_at": data.get("captured_at")}


@dataclass
class SchemaDiff:
    """Differences between a baseline and live schema."""
    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    added_relationships: list[str] = field(default_factory=list)
    removed_relationships: list[str] = field(default_factory=list)
    # label -> list of property-level changes
    node_property_changes: dict[str, list[str]] = field(default_factory=dict)
    relationship_property_changes: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.added_nodes or self.removed_nodes
            or self.added_relationships or self.removed_relationships
            or self.node_property_changes or self.relationship_property_changes
        )


def diff_schemas(baseline: GraphSchema, live: GraphSchema) -> SchemaDiff:
    """Compare baseline against live schema and return differences."""
    d = SchemaDiff()

    base_nodes = set(baseline.nodes)
    live_nodes = set(live.nodes)
    d.added_nodes = sorted(live_nodes - base_nodes)
    d.removed_nodes = sorted(base_nodes - live_nodes)

    for label in base_nodes & live_nodes:
        base_props = set(baseline.nodes[label].properties)
        live_props = set(live.nodes[label].properties)
        changes = []
        for p in sorted(live_props - base_props):
            changes.append(f"added property '{p}'")
        for p in sorted(base_props - live_props):
            changes.append(f"removed property '{p}'")
        for p in sorted(base_props & live_props):
            bt = baseline.nodes[label].properties[p]
            lt = live.nodes[label].properties[p]
            if bt != lt:
                changes.append(f"property '{p}' type changed: {bt} -> {lt}")
        if changes:
            d.node_property_changes[label] = changes

    base_rels = set(baseline.relationships)
    live_rels = set(live.relationships)
    d.added_relationships = sorted(live_rels - base_rels)
    d.removed_relationships = sorted(base_rels - live_rels)

    for rt in base_rels & live_rels:
        base_r = baseline.relationships[rt]
        live_r = live.relationships[rt]
        changes = []
        if base_r.source_labels != live_r.source_labels:
            changes.append(f"source_labels changed: {base_r.source_labels} -> {live_r.source_labels}")
        if base_r.target_labels != live_r.target_labels:
            changes.append(f"target_labels changed: {base_r.target_labels} -> {live_r.target_labels}")
        base_props = set(base_r.properties)
        live_props = set(live_r.properties)
        for p in sorted(live_props - base_props):
            changes.append(f"added property '{p}'")
        for p in sorted(base_props - live_props):
            changes.append(f"removed property '{p}'")
        for p in sorted(base_props & live_props):
            if base_r.properties[p] != live_r.properties[p]:
                changes.append(f"property '{p}' type changed: {base_r.properties[p]} -> {live_r.properties[p]}")
        if changes:
            d.relationship_property_changes[rt] = changes

    return d
