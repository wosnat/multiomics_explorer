"""P1: Tests for schema diffing, baseline round-trip, and prompt formatting."""

import tempfile
from pathlib import Path

import pytest

from multiomics_explorer.kg.schema import (
    GraphSchema,
    NodeSchema,
    RelationshipSchema,
    SchemaDiff,
    diff_schemas,
    load_baseline,
    save_baseline,
)


def _make_schema(
    nodes: dict | None = None,
    relationships: dict | None = None,
) -> GraphSchema:
    """Helper to build a GraphSchema from simple dicts."""
    schema = GraphSchema()
    for label, props in (nodes or {}).items():
        schema.nodes[label] = NodeSchema(label=label, count=10, properties=props)
    for rtype, info in (relationships or {}).items():
        schema.relationships[rtype] = RelationshipSchema(
            type=rtype,
            source_labels=info.get("src", []),
            target_labels=info.get("tgt", []),
            properties=info.get("props", {}),
        )
    return schema


class TestDiffNodes:
    def test_identical_schemas_no_changes(self):
        s = _make_schema(nodes={"Gene": {"locus_tag": "string"}})
        diff = diff_schemas(s, s)
        assert not diff.has_changes

    def test_added_node_label(self):
        base = _make_schema(nodes={"Gene": {}})
        live = _make_schema(nodes={"Gene": {}, "Protein": {}})
        diff = diff_schemas(base, live)
        assert "Protein" in diff.added_nodes
        assert diff.has_changes

    def test_removed_node_label(self):
        base = _make_schema(nodes={"Gene": {}, "Protein": {}})
        live = _make_schema(nodes={"Gene": {}})
        diff = diff_schemas(base, live)
        assert "Protein" in diff.removed_nodes
        assert diff.has_changes

    def test_added_node_property(self):
        base = _make_schema(nodes={"Gene": {"locus_tag": "string"}})
        live = _make_schema(nodes={"Gene": {"locus_tag": "string", "name": "string"}})
        diff = diff_schemas(base, live)
        assert "Gene" in diff.node_property_changes
        assert any("added property 'name'" in c for c in diff.node_property_changes["Gene"])

    def test_removed_node_property(self):
        base = _make_schema(nodes={"Gene": {"locus_tag": "string", "name": "string"}})
        live = _make_schema(nodes={"Gene": {"locus_tag": "string"}})
        diff = diff_schemas(base, live)
        assert "Gene" in diff.node_property_changes
        assert any("removed property 'name'" in c for c in diff.node_property_changes["Gene"])

    def test_changed_node_property_type(self):
        base = _make_schema(nodes={"Gene": {"score": "int"}})
        live = _make_schema(nodes={"Gene": {"score": "float"}})
        diff = diff_schemas(base, live)
        assert "Gene" in diff.node_property_changes
        assert any("type changed: int -> float" in c for c in diff.node_property_changes["Gene"])


class TestDiffRelationships:
    def test_added_relationship_type(self):
        base = _make_schema(relationships={
            "ENCODES": {"src": ["Gene"], "tgt": ["Protein"]},
        })
        live = _make_schema(relationships={
            "ENCODES": {"src": ["Gene"], "tgt": ["Protein"]},
            "BELONGS_TO": {"src": ["Gene"], "tgt": ["Organism"]},
        })
        diff = diff_schemas(base, live)
        assert "BELONGS_TO" in diff.added_relationships

    def test_removed_relationship_type(self):
        base = _make_schema(relationships={
            "ENCODES": {"src": ["Gene"], "tgt": ["Protein"]},
            "BELONGS_TO": {"src": ["Gene"], "tgt": ["Organism"]},
        })
        live = _make_schema(relationships={
            "ENCODES": {"src": ["Gene"], "tgt": ["Protein"]},
        })
        diff = diff_schemas(base, live)
        assert "BELONGS_TO" in diff.removed_relationships

    def test_added_edge_property(self):
        base = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene"], "props": {"log2fc": "float"}},
        })
        live = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene"], "props": {"log2fc": "float", "pvalue": "float"}},
        })
        diff = diff_schemas(base, live)
        assert "EXPR" in diff.relationship_property_changes
        assert any("added property 'pvalue'" in c for c in diff.relationship_property_changes["EXPR"])

    def test_removed_edge_property(self):
        base = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene"], "props": {"log2fc": "float", "pvalue": "float"}},
        })
        live = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene"], "props": {"log2fc": "float"}},
        })
        diff = diff_schemas(base, live)
        assert "EXPR" in diff.relationship_property_changes
        assert any("removed property 'pvalue'" in c for c in diff.relationship_property_changes["EXPR"])

    def test_changed_edge_property_type(self):
        base = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene"], "props": {"log2fc": "int"}},
        })
        live = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene"], "props": {"log2fc": "float"}},
        })
        diff = diff_schemas(base, live)
        assert "EXPR" in diff.relationship_property_changes
        assert any("type changed: int -> float" in c for c in diff.relationship_property_changes["EXPR"])

    def test_changed_source_labels(self):
        base = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene"], "props": {}},
        })
        live = _make_schema(relationships={
            "EXPR": {"src": ["Org", "Condition"], "tgt": ["Gene"], "props": {}},
        })
        diff = diff_schemas(base, live)
        assert "EXPR" in diff.relationship_property_changes
        assert any("source_labels changed" in c for c in diff.relationship_property_changes["EXPR"])

    def test_changed_target_labels(self):
        base = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene"], "props": {}},
        })
        live = _make_schema(relationships={
            "EXPR": {"src": ["Org"], "tgt": ["Gene", "Protein"], "props": {}},
        })
        diff = diff_schemas(base, live)
        assert "EXPR" in diff.relationship_property_changes
        assert any("target_labels changed" in c for c in diff.relationship_property_changes["EXPR"])


class TestBaselineRoundTrip:
    def test_save_and_load(self, tmp_path):
        schema = _make_schema(
            nodes={"Gene": {"locus_tag": "string", "product": "string"}},
            relationships={
                "ENCODES": {
                    "src": ["Gene"], "tgt": ["Protein"],
                    "props": {"score": "float"},
                },
            },
        )
        path = tmp_path / "baseline.yaml"
        save_baseline(schema, path=path)

        loaded, meta = load_baseline(path=path)
        assert "Gene" in loaded.nodes
        assert loaded.nodes["Gene"].properties["locus_tag"] == "string"
        assert "ENCODES" in loaded.relationships
        assert loaded.relationships["ENCODES"].properties["score"] == "float"
        assert loaded.relationships["ENCODES"].source_labels == ["Gene"]
        assert meta["version"] == 1
        assert meta["captured_at"] is not None

    def test_round_trip_produces_empty_diff(self, tmp_path):
        schema = _make_schema(
            nodes={"Gene": {"locus_tag": "string"}},
            relationships={"ENCODES": {"src": ["Gene"], "tgt": ["Protein"], "props": {}}},
        )
        path = tmp_path / "baseline.yaml"
        save_baseline(schema, path=path)
        loaded, _ = load_baseline(path=path)
        diff = diff_schemas(schema, loaded)
        assert not diff.has_changes


class TestPromptString:
    def test_contains_node_labels(self):
        schema = _make_schema(nodes={"Gene": {"locus_tag": "string"}})
        text = schema.to_prompt_string()
        assert "Gene" in text
        assert "locus_tag" in text

    def test_contains_relationship_types(self):
        schema = _make_schema(relationships={
            "ENCODES": {"src": ["Gene"], "tgt": ["Protein"], "props": {"score": "float"}},
        })
        text = schema.to_prompt_string()
        assert "ENCODES" in text
        assert "Gene" in text
        assert "Protein" in text
        assert "score" in text

    def test_has_markdown_structure(self):
        schema = _make_schema(
            nodes={"Gene": {}},
            relationships={"ENCODES": {"src": ["Gene"], "tgt": ["Protein"], "props": {}}},
        )
        text = schema.to_prompt_string()
        assert "## Graph Schema" in text
        assert "### Node Types" in text
        assert "### Relationship Types" in text
