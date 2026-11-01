"""Graph schema introspection from the live Neo4j instance."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

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


# Per-process caches keyed by KG endpoint (restart the server after a KG
# rebuild, as for the other per-process caches); fakes / custom conns are
# never cached. `_PROPERTIES_CACHE` holds one property map per
# (endpoint, kind, type name); `_NODE_CATALOG_CACHE` the whole-graph
# `db.schema.nodeTypeProperties()` read (~5 s).
_PROPERTIES_CACHE: dict[tuple, dict[str, str]] = {}
_NODE_CATALOG_CACHE: dict[tuple, dict[str, dict[str, str]]] = {}
_DECLARED_CACHE: dict[tuple, dict[str, dict]] = {}

# Set by BioCypher on every node / edge it writes, never declared in
# schema_config.yaml; a declared type learns which ones it carries from one
# row (they are dense, so any row answers).
_BIOCYPHER_KEYS = ("id", "preferred_id", "source", "licence", "version")

# schema_config.yaml type spellings -> `_infer_type` names.
_DECLARED_TYPES = {
    "str": "string", "int": "int", "float": "float",
    "bool": "boolean", "boolean": "boolean",
}

_PROCEDURE_TYPES = {
    "String": "string", "Long": "int", "Double": "float", "Boolean": "boolean",
}


def _endpoint(conn: GraphConnection) -> tuple | None:
    settings = getattr(conn, "_settings", None)
    if isinstance(conn, GraphConnection) and settings is not None:
        return (settings.neo4j_uri, settings.neo4j_database)
    return None


def _procedure_type(types: list[str] | None) -> str:
    """Map `db.schema.*TypeProperties` type names to `_infer_type` names."""
    for t in sorted(types or []):
        if t.endswith("Array"):
            return "list"
        if t in _PROCEDURE_TYPES:
            return _PROCEDURE_TYPES[t]
    return "any"


def _declared_type(t: Any) -> str:
    t = str(t)
    if t.endswith("[]") or t.startswith("list"):
        return "list"
    return _DECLARED_TYPES.get(t, "any")


def _schema_label(key: str, entry: dict) -> str:
    """BioCypher's Neo4j label / relationship type for a schema_config entry
    (same rule as the KG's `tests/kg_validity/test_schema_coverage.py`)."""
    label_as_edge = entry.get("label_as_edge")
    if label_as_edge:
        return label_as_edge[0].upper() + label_as_edge[1:]
    return "".join(w[:1].upper() + w[1:] for w in key.replace("_", " ").split())


def _declared_schema(conn: GraphConnection) -> dict[str, dict]:
    """What the KG declares in `Schema_info.schema_info` (the JSON dump of
    its schema_config.yaml): ``{"properties": {label_or_type: {prop: type}},
    "endpoints": {rel_type: (source_labels, target_labels)}}``.

    The KG build guarantees every live property is declared, post-import
    ones included (`test_schema_coverage.py`), so a declared type needs no
    graph query at all. Abstract BioCypher parents (NamedThing, Entity, ...)
    and Schema_info itself are not declared; an older KG without the node
    yields empty maps.
    """
    endpoint = _endpoint(conn)
    if endpoint is not None and endpoint in _DECLARED_CACHE:
        return _DECLARED_CACHE[endpoint]
    properties: dict[str, dict[str, str]] = {}
    endpoints: dict[str, tuple[set[str], set[str]]] = {}
    try:
        rows = conn.execute_query(
            "MATCH (s:Schema_info) RETURN s.schema_info AS schema LIMIT 1"
        )
        raw = rows[0].get("schema") if rows else None
        schema = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (ValueError, TypeError, IndexError, AttributeError):
        schema = {}
    if not isinstance(schema, dict):
        schema = {}
    entries = {
        key: entry for key, entry in schema.items()
        if isinstance(entry, dict) and "represented_as" in entry
    }
    node_labels = {
        key: _schema_label(key, entry) for key, entry in entries.items()
        if entry.get("represented_as") == "node"
    }

    def _labels(ref: Any) -> set[str]:
        refs = ref if isinstance(ref, list) else [ref]
        return {node_labels.get(r) or _schema_label(str(r), {}) for r in refs if r}

    for key, entry in entries.items():
        label = _schema_label(key, entry)
        props = properties.setdefault(label, {})
        for name, t in (entry.get("properties") or {}).items():
            props[name] = _declared_type(t)
        if entry.get("represented_as") == "edge" and entry.get("source") and entry.get("target"):
            src, tgt = endpoints.setdefault(label, (set(), set()))
            src.update(_labels(entry["source"]))
            tgt.update(_labels(entry["target"]))
    declared = {
        "properties": properties,
        "endpoints": {
            rt: (sorted(src), sorted(tgt)) for rt, (src, tgt) in endpoints.items()
        },
    }
    if endpoint is not None:
        _DECLARED_CACHE[endpoint] = declared
    return declared


def _declared_properties(conn: GraphConnection) -> dict[str, dict[str, str]]:
    """label / relationship type -> {property: type} from `_declared_schema`."""
    return _declared_schema(conn)["properties"]


def _node_catalog(conn: GraphConnection) -> dict[str, dict[str, str]]:
    """label -> {property: type} over every node in the graph, from
    `db.schema.nodeTypeProperties()` (a full scan, not a sample); abstract
    parent labels are left out (see below)."""
    endpoint = _endpoint(conn)
    if endpoint is not None and endpoint in _NODE_CATALOG_CACHE:
        return _NODE_CATALOG_CACHE[endpoint]
    catalog: dict[str, dict[str, str]] = {}
    rows = conn.execute_query(
        "CALL db.schema.nodeTypeProperties() "
        "YIELD nodeLabels, propertyName, propertyTypes "
        "RETURN nodeLabels, propertyName, propertyTypes"
    )
    # BioCypher stamps every ancestor label on a node (Gene also carries
    # BiologicalEntity, NamedThing, Entity, ...). A label takes a row's
    # properties only when it is the most specific label of that row's
    # combination (fewest distinct combinations containing it), so abstract
    # parents keep their sampled properties instead of every child's.
    combos = {tuple(sorted(r.get("nodeLabels") or [])) for r in rows}
    spread: dict[str, int] = {}
    for combo in combos:
        for label in combo:
            spread[label] = spread.get(label, 0) + 1
    for row in rows:
        name = row.get("propertyName")
        labels = row.get("nodeLabels") or []
        if not name or not labels:
            continue
        narrowest = min(spread[label] for label in labels)
        for label in labels:
            if spread[label] != narrowest:
                continue
            props = catalog.setdefault(label, {})
            if props.get(name, "any") == "any":
                props[name] = _procedure_type(row.get("propertyTypes"))
    if endpoint is not None:
        _NODE_CATALOG_CACHE[endpoint] = catalog
    return catalog


def _type_properties(conn: GraphConnection, kind: str, name: str) -> dict[str, str]:
    """Property name -> type for one node label (``kind='node'``) or
    relationship type (``kind='rel'``).

    The key set covers *every* node / edge of the type, so a sparse property
    (e.g. ``rank_up``, set only on significant-up expression edges) is listed
    regardless of whether a sample hits it. A type the KG declares in
    `Schema_info` takes its keys and types from the declaration, plus the
    BioCypher keys (``id``, ``preferred_id``, ...) one row carries. On a declaring KG an undeclared label is either an abstract
    BioCypher parent (its nodes carry a declared label; no properties of its
    own) or Schema_info itself (a 10-row sample). A KG without a declaration
    falls back to scanning: keys the sample missed come from
    `db.schema.nodeTypeProperties()` (nodes) or from the first carrier found
    (relationships; one batched query per type).
    """
    endpoint = _endpoint(conn)
    cache_key = (*endpoint, kind, name) if endpoint is not None else None
    if cache_key is not None and cache_key in _PROPERTIES_CACHE:
        return dict(_PROPERTIES_CACHE[cache_key])

    declared_all = _declared_properties(conn)
    declared = declared_all.get(name)
    if declared is not None:
        match = f"MATCH (n:`{name}`)" if kind == "node" else f"MATCH ()-[n:`{name}`]->()"
        probe = conn.execute_query(f"{match} RETURN keys(n) AS keys LIMIT 1")
        keys = set((probe[0].get("keys") if probe else None) or [])
        props = {k: "string" for k in _BIOCYPHER_KEYS if k in keys}
        props.update(declared)
        if cache_key is not None:
            _PROPERTIES_CACHE[cache_key] = dict(props)
        return props

    if kind == "node" and declared_all:
        # An undeclared label whose nodes carry a declared label is an
        # abstract BioCypher parent (NamedThing, Entity, ...): no properties
        # of its own. One node decides it; no scan.
        probe = conn.execute_query(
            f"MATCH (n:`{name}`) RETURN labels(n) AS labels LIMIT 1"
        )
        node_labels = (probe[0].get("labels") if probe else None) or []
        if any(label in declared_all for label in node_labels if label != name):
            if cache_key is not None:
                _PROPERTIES_CACHE[cache_key] = {}
            return {}

    if kind == "node":
        match, var, order = f"MATCH (n:`{name}`)", "n", "coalesce(n.id, elementId(n))"
    else:
        match, var, order = f"MATCH ()-[r:`{name}`]->()", "r", "elementId(r)"

    props: dict[str, str] = {}
    sample = conn.execute_query(
        f"{match} RETURN properties({var}) AS props ORDER BY {order} LIMIT 10"
    )
    for row in sample:
        if row.get("props"):
            for k, v in row["props"].items():
                if k not in props or props[k] == "any":
                    props[k] = _infer_type(v)

    if declared_all:
        pass  # declared KG: an undeclared concrete label (Schema_info) keeps its sample
    elif kind == "node":
        for k, t in sorted(_node_catalog(conn).get(name, {}).items()):
            if props.get(k, "any") == "any":
                props[k] = t
    else:
        all_keys = conn.execute_query(
            f"{match} UNWIND keys({var}) AS k RETURN DISTINCT k"
        )
        missing = sorted({row.get("k") for row in all_keys} - set(props) - {None})
        if missing:
            fill = conn.execute_query(
                f"UNWIND $keys AS k CALL {{ WITH k {match} WHERE {var}[k] IS NOT NULL "
                f"RETURN {var}[k] AS v LIMIT 1 }} RETURN k, v",
                keys=missing,
            )
            found = {row.get("k"): row.get("v") for row in fill}
            for k in missing:
                props[k] = _infer_type(found.get(k))

    if cache_key is not None:
        _PROPERTIES_CACHE[cache_key] = dict(props)
    return props


def load_schema_from_neo4j(
    conn: GraphConnection,
    *,
    labels: list[str] | None = None,
    relationship_types: list[str] | None = None,
    section: Literal["nodes", "relationships", "both"] = "both",
    with_counts: bool = True,
) -> GraphSchema:
    """Introspect the graph schema from a live Neo4j instance.

    Queries node labels, relationship types, and samples properties
    from each to build a GraphSchema object.

    ``labels`` / ``relationship_types``, when given, restrict introspection
    to exactly those (already-validated) values instead of enumerating
    every label / relationship type in the graph — the caller is expected
    to have resolved unknown values before calling in (see
    ``api.functions.kg_schema``). ``section`` skips introspecting the other
    half entirely (no catalog call for it). ``with_counts=False`` skips the
    per-label node counts (``kg_schema`` does not return them).

    On a KG that declares its schema in `Schema_info`, relationship
    endpoints are the declared source / target labels (concrete labels
    only, no BioCypher ancestors) and properties come from the declaration;
    a full dump then costs a handful of cheap queries.

    Property keys are the union over every node / edge of the type
    (``_type_properties``: the KG's `Schema_info` declaration where it has
    one, a graph scan otherwise), so sparse properties are always listed;
    sampled types come from a deterministically ordered sample (``coalesce(n.id, elementId(n))`` for nodes,
    ``elementId(r)`` for relationships), stable across builds even for
    abstract labels that lack an ``id`` property. See ``_type_properties``.
    """
    schema = GraphSchema()

    if section in ("nodes", "both"):
        target_labels = labels if labels is not None else conn.get_labels()
        for label in target_labels:
            count = conn.get_node_count(label) if with_counts else 0
            node_schema = NodeSchema(label=label, count=count)

            node_schema.properties = _type_properties(conn, "node", label)

            schema.nodes[label] = node_schema

    if section in ("relationships", "both"):
        declared_endpoints = _declared_schema(conn)["endpoints"]
        target_rel_types = relationship_types if relationship_types is not None else conn.get_relationship_types()
        for rel_type in target_rel_types:
            rel_schema = RelationshipSchema(type=rel_type)

            declared_ends = declared_endpoints.get(rel_type)
            if declared_ends is not None:
                rel_schema.source_labels, rel_schema.target_labels = (
                    list(declared_ends[0]), list(declared_ends[1]),
                )
                rel_schema.properties = _type_properties(conn, "rel", rel_type)
                schema.relationships[rel_type] = rel_schema
                continue

            # Undeclared (older KG): source and target labels from the graph
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

            rel_schema.properties = _type_properties(conn, "rel", rel_type)

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
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    return path


def load_baseline(path: Path = BASELINE_PATH) -> tuple[GraphSchema, dict]:
    """Load baseline schema from YAML. Returns (schema, metadata)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
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
