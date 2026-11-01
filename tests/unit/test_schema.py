"""P1: Tests for schema diffing, baseline round-trip, prompt formatting, and
introspection scoping/determinism."""

import json
from unittest.mock import MagicMock

from multiomics_explorer.kg.schema import (
    GraphSchema,
    NodeSchema,
    RelationshipSchema,
    diff_schemas,
    load_baseline,
    load_schema_from_neo4j,
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


class TestLoadSchemaFromNeo4jScoping:
    """`labels` / `relationship_types` / `section` restrict introspection to
    exactly the requested (already-validated) values, without enumerating
    the full catalog."""

    def test_specific_labels_skips_get_labels(self):
        conn = MagicMock()
        conn.get_node_count.return_value = 5
        conn.execute_query.return_value = [{"props": {"locus_tag": "string"}}]

        schema = load_schema_from_neo4j(conn, labels=["Gene"], section="nodes")

        conn.get_labels.assert_not_called()
        conn.get_node_count.assert_called_once_with("Gene")
        assert set(schema.nodes) == {"Gene"}

    def test_labels_none_enumerates_all(self):
        conn = MagicMock()
        conn.get_labels.return_value = ["Gene", "Experiment"]
        conn.get_node_count.return_value = 1
        conn.execute_query.return_value = []

        schema = load_schema_from_neo4j(conn, section="nodes")

        conn.get_labels.assert_called_once()
        assert set(schema.nodes) == {"Gene", "Experiment"}

    def test_section_nodes_skips_relationship_introspection(self):
        conn = MagicMock()
        conn.get_node_count.return_value = 1
        conn.execute_query.return_value = []

        schema = load_schema_from_neo4j(conn, labels=["Gene"], section="nodes")

        conn.get_relationship_types.assert_not_called()
        assert schema.relationships == {}

    def test_section_relationships_skips_node_introspection(self):
        conn = MagicMock()
        conn.get_relationship_types.return_value = ["Encodes"]
        conn.execute_query.return_value = []

        schema = load_schema_from_neo4j(conn, section="relationships")

        conn.get_labels.assert_not_called()
        conn.get_node_count.assert_not_called()
        assert schema.nodes == {}

    def test_specific_relationship_types_skips_get_relationship_types(self):
        conn = MagicMock()
        conn.execute_query.return_value = []

        schema = load_schema_from_neo4j(
            conn, relationship_types=["Encodes"], section="relationships",
        )

        conn.get_relationship_types.assert_not_called()
        assert set(schema.relationships) == {"Encodes"}

    def test_node_property_sample_is_ordered_deterministically(self):
        conn = MagicMock()
        conn.get_node_count.return_value = 1
        conn.execute_query.return_value = []

        load_schema_from_neo4j(conn, labels=["Gene"], section="nodes")

        cypher = next(
            c.args[0] for c in conn.execute_query.call_args_list
            if "properties(n)" in c.args[0]
        )
        assert "ORDER BY coalesce(n.id, elementId(n))" in cypher
        assert "LIMIT 10" in cypher

    def test_relationship_property_sample_is_ordered_deterministically(self):
        conn = MagicMock()
        conn.execute_query.return_value = []

        load_schema_from_neo4j(
            conn, relationship_types=["Encodes"], section="relationships",
        )

        prop_calls = [
            c.args[0] for c in conn.execute_query.call_args_list
            if "properties(r)" in c.args[0]
        ]
        assert len(prop_calls) == 1
        assert "ORDER BY elementId(r)" in prop_calls[0]
        assert "LIMIT 10" in prop_calls[0]


def _routing_conn(sample_props, all_keys, fill_values, declared=None):
    """Fake conn answering the property queries by shape: the Schema_info
    declaration, the 10-row sample, the full-type key union, and the
    per-key fill."""
    conn = MagicMock()
    conn.get_node_count.return_value = 1

    def execute(cypher, **params):
        if "Schema_info" in cypher:
            return [{"schema": json.dumps(declared)}] if declared else []
        if "nodeTypeProperties" in cypher:
            names = {int: "Long", float: "Double", str: "String"}
            return [
                {"nodeLabels": ["Gene"], "propertyName": k,
                 "propertyTypes": [names[type(fill_values[k])]]}
                for k in all_keys if k in fill_values
            ]
        if "properties(" in cypher:
            return [{"props": p} for p in sample_props]
        if "DISTINCT k" in cypher:
            return [{"k": k} for k in all_keys]
        if "AS v" in cypher:
            return [{"k": k, "v": fill_values[k]} for k in params["keys"]]
        return []

    conn.execute_query.side_effect = execute
    return conn


class TestSparseProperties:
    """Properties set on only a few nodes/edges must not depend on whether
    the 10-row sample happens to hit one (backlog 3.20: `rank_up` on
    `Changes_expression_of` dropped out after a rebuild)."""

    def test_sparse_relationship_property_is_listed_with_its_type(self):
        conn = _routing_conn(
            sample_props=[{"log2_fold_change": 1.5}],
            all_keys=["log2_fold_change", "rank_up"],
            fill_values={"rank_up": 3},
        )
        schema = load_schema_from_neo4j(
            conn, relationship_types=["Changes_expression_of"],
            section="relationships",
        )
        props = schema.relationships["Changes_expression_of"].properties
        assert props == {"log2_fold_change": "float", "rank_up": "int"}

    def test_sparse_node_property_is_listed_with_its_type(self):
        conn = _routing_conn(
            sample_props=[{"locus_tag": "PMM0001"}],
            all_keys=["locus_tag", "gene_name"],
            fill_values={"gene_name": "dnaN"},
        )
        schema = load_schema_from_neo4j(conn, labels=["Gene"], section="nodes")
        assert schema.nodes["Gene"].properties == {
            "locus_tag": "string", "gene_name": "string",
        }

    def test_sampled_keys_are_not_refetched(self):
        conn = _routing_conn(
            sample_props=[{"log2_fold_change": 1.5}],
            all_keys=["log2_fold_change"],
            fill_values={},
        )
        load_schema_from_neo4j(
            conn, relationship_types=["Changes_expression_of"],
            section="relationships",
        )
        fills = [c for c in conn.execute_query.call_args_list if "AS v" in c.args[0]]
        assert fills == []


class TestDeclaredProperties:
    """A type the KG declares in `Schema_info.schema_info` takes its keys and
    types from the declaration; no full-graph scan runs for it."""

    DECLARED = {
        "changes expression of": {
            "represented_as": "edge",
            "label_as_edge": "changes_expression_of",
            "properties": {"log2_fold_change": "float", "rank_up": "int",
                           "treatment_type": "str[]"},
        },
        "gene": {"represented_as": "node",
                 "properties": {"locus_tag": "str", "gene_count": "int"}},
        "taxonomy": {"some": "metadata"},
    }

    def _scans(self, conn):
        return [c for c in conn.execute_query.call_args_list
                if any(m in c.args[0] for m in
                       ("DISTINCT k", "AS v", "nodeTypeProperties"))]

    def test_declared_relationship_needs_no_scan(self):
        conn = _routing_conn(
            sample_props=[{"log2_fold_change": 1.5}],
            all_keys=[], fill_values={}, declared=self.DECLARED,
        )
        schema = load_schema_from_neo4j(
            conn, relationship_types=["Changes_expression_of"],
            section="relationships",
        )
        assert schema.relationships["Changes_expression_of"].properties == {
            "log2_fold_change": "float", "rank_up": "int",
            "treatment_type": "list",
        }
        assert self._scans(conn) == []

    def test_declared_node_label_needs_no_scan(self):
        conn = _routing_conn(
            sample_props=[{"locus_tag": "PMM0001"}],
            all_keys=[], fill_values={}, declared=self.DECLARED,
        )
        schema = load_schema_from_neo4j(conn, labels=["Gene"], section="nodes")
        assert schema.nodes["Gene"].properties == {
            "locus_tag": "string", "gene_count": "int",
        }
        assert self._scans(conn) == []

    def test_sampled_key_missing_from_declaration_is_kept(self):
        conn = _routing_conn(
            sample_props=[{"locus_tag": "PMM0001", "legacy": 2}],
            all_keys=[], fill_values={}, declared=self.DECLARED,
        )
        schema = load_schema_from_neo4j(conn, labels=["Gene"], section="nodes")
        assert schema.nodes["Gene"].properties["legacy"] == "int"

    def test_undeclared_label_falls_back_to_scan(self):
        conn = _routing_conn(
            sample_props=[{"locus_tag": "PMM0001"}],
            all_keys=["locus_tag", "gene_name"],
            fill_values={"gene_name": "dnaN"}, declared=self.DECLARED,
        )
        schema = load_schema_from_neo4j(
            conn, labels=["NamedThing"], section="nodes",
        )
        assert "nodeTypeProperties" in " ".join(
            c.args[0] for c in conn.execute_query.call_args_list
        )
        assert schema.nodes["NamedThing"].properties == {"locus_tag": "string"}


class TestAbstractLabels:
    """BioCypher parent labels (NamedThing, Entity, ...) sit on every node;
    they must not collect every child label's properties from the catalog."""

    def _conn(self):
        conn = MagicMock()
        conn.get_node_count.return_value = 1

        def execute(cypher, **params):
            if "nodeTypeProperties" in cypher:
                return [
                    {"nodeLabels": ["Gene", "NamedThing"],
                     "propertyName": "locus_tag", "propertyTypes": ["String"]},
                    {"nodeLabels": ["Gene", "NamedThing"],
                     "propertyName": "rank_hint", "propertyTypes": ["Long"]},
                    {"nodeLabels": ["Protein", "NamedThing"],
                     "propertyName": "sequence_length", "propertyTypes": ["Long"]},
                ]
            return []

        conn.execute_query.side_effect = execute
        return conn

    def test_concrete_label_gets_catalog_properties(self):
        schema = load_schema_from_neo4j(self._conn(), labels=["Gene"], section="nodes")
        assert schema.nodes["Gene"].properties == {
            "locus_tag": "string", "rank_hint": "int",
        }

    def test_abstract_label_does_not_collect_child_properties(self):
        schema = load_schema_from_neo4j(
            self._conn(), labels=["NamedThing"], section="nodes")
        assert schema.nodes["NamedThing"].properties == {}
