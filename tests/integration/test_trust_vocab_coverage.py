"""ControlledVocabulary coverage for every filterable / rolled-up trust prop.

The registry declares *shape* — which axes an ontology's gene edge carries,
which categoricals are compact, which native detail is verbose. The graph's
`ControlledVocabulary` nodes declare *values*. `list_filter_values` reads the
vocabulary node and only falls back to a pivot-over-the-graph (plus a warning)
when the node is missing, so a KG rebuild that drops one degrades the whole
trust-discovery surface silently.

These tests fail loudly instead, naming the missing `applies_to` / `property`
so the report routes to the KG team.

All tests are `-m kg`: they read the live build.
"""

import pytest

from multiomics_explorer.api import functions as api
from multiomics_explorer.kg.queries_lib import (
    ONTOLOGY_CONFIG,
    _verbose_edge_pairs,
    ontology_trust_axes,
)


# ---------------------------------------------------------------------------
# What must have a vocabulary node
# ---------------------------------------------------------------------------

# Numeric axes are ranges, not value sets — the vocabulary node carries
# min_value / max_value for them, so they are still required to exist.
_TRUST_AXIS_PROPS = ("sources", "evidence", "evidence_score", "tier")

# `verbose_edge` props that back a `list_filter_values` filter_type. The rest
# are free scalars (e-values, coordinates, bit scores) with no value set.
_VERBOSE_EDGE_FILTERABLE = {
    spec["prop"]
    for spec in api._TRUST_FILTER_VALUE_SPECS.values()
    if spec.get("scope") == "verbose_edge"
}

# Node-side facets / term categoricals exposed as filter types.
_NODE_FILTER_SPECS = {
    name: spec
    for name, spec in api._TRUST_FILTER_VALUE_SPECS.items()
    if spec["kind"] == "node"
}


def _edge_vocab_targets() -> list[tuple[str, str, str, str]]:
    """(ontology, gene_rel, prop, why) for every edge prop needing a vocab."""
    out: list[tuple[str, str, str, str]] = []
    for key, cfg in ONTOLOGY_CONFIG.items():
        rel = cfg.get("gene_rel")
        if not rel:
            continue
        trust = cfg.get("trust") or {}
        for axis in _TRUST_AXIS_PROPS:
            if axis in ontology_trust_axes(key):
                out.append((key, rel, trust[axis], f"trust axis {axis}"))
        for name, spec in (cfg.get("compact_edge") or {}).items():
            out.append((key, rel, spec["prop"], f"compact_edge {name}"))
        for prop, _column in _verbose_edge_pairs(cfg):
            if prop in _VERBOSE_EDGE_FILTERABLE:
                out.append((key, rel, prop, "filterable verbose_edge"))
    # De-duplicate: several ontologies share neither rel nor prop today, but
    # the parametrization must stay stable if one ever does.
    seen: dict[tuple[str, str], tuple] = {}
    for entry in out:
        seen.setdefault((entry[1], entry[2]), entry)
    return sorted(seen.values())


_EDGE_TARGETS = _edge_vocab_targets()
_EDGE_IDS = [f"{o}:{prop}" for o, _rel, prop, _why in _EDGE_TARGETS]


def _vocab_row(conn, applies_to: str, prop: str):
    rows = conn.execute_query(
        "MATCH (v:ControlledVocabulary "
        "{applies_to: $applies_to, property: $prop}) "
        "RETURN v.values AS values, v.value_type AS value_type, "
        "       v.description AS description, v.min_value AS min_value, "
        "       v.max_value AS max_value",
        applies_to=applies_to, prop=prop,
    )
    return rows[0] if rows else None


@pytest.mark.kg
class TestEdgeTrustVocabularies:
    """Every filtered / rolled-up gene-edge property has a vocabulary node."""

    @pytest.mark.parametrize(
        "ontology,rel,prop,why", _EDGE_TARGETS, ids=_EDGE_IDS,
    )
    def test_controlled_vocabulary_node_exists(
        self, conn, ontology, rel, prop, why,
    ):
        row = _vocab_row(conn, rel, prop)
        assert row is not None, (
            f"No ControlledVocabulary node for applies_to='{rel}', "
            f"property='{prop}' ({ontology}, {why}). Without it "
            f"list_filter_values degrades to a pivot query plus a warning. "
            f"This is a KG-side node, not an explorer-side one."
        )

    @pytest.mark.parametrize(
        "ontology,rel,prop,why", _EDGE_TARGETS, ids=_EDGE_IDS,
    )
    def test_vocabulary_node_carries_values_or_a_range(
        self, conn, ontology, rel, prop, why,
    ):
        row = _vocab_row(conn, rel, prop)
        assert row is not None, f"{rel}.{prop} vocabulary node is missing"
        has_values = bool(row.get("values"))
        has_range = (
            row.get("min_value") is not None
            or row.get("max_value") is not None
        )
        assert has_values or has_range, (
            f"ControlledVocabulary {rel}.{prop} declares neither `values` "
            f"nor a min/max range — nothing for list_filter_values to serve."
        )


@pytest.mark.kg
class TestNodeFacetVocabularies:
    """Term-side facets and categoricals resolve the same way."""

    @pytest.mark.parametrize("filter_type", sorted(_NODE_FILTER_SPECS))
    def test_controlled_vocabulary_node_exists(self, conn, filter_type):
        spec = _NODE_FILTER_SPECS[filter_type]
        labels = [
            ONTOLOGY_CONFIG[o]["label"] for o in spec.get("ontologies", [])
        ]
        assert labels, f"{filter_type} names no owning ontology"
        for label in labels:
            row = _vocab_row(conn, label, spec["prop"])
            assert row is not None, (
                f"No ControlledVocabulary node for applies_to='{label}', "
                f"property='{spec['prop']}' (filter_type='{filter_type}')."
            )


@pytest.mark.kg
class TestListFilterValuesReadsTheVocabulary:
    """The tool must resolve from the vocabulary, never from a pivot."""

    @pytest.mark.parametrize(
        "filter_type", sorted(api._TRUST_FILTER_VALUE_SPECS),
    )
    def test_no_pivot_fallback_warning(self, conn, filter_type):
        api._reset_vocab_cache()
        result = api.list_filter_values(filter_type=filter_type, conn=conn)
        assert result["results"], f"{filter_type} returned no values"
        assert result.get("warnings", []) == [], (
            f"list_filter_values(filter_type='{filter_type}') fell back to a "
            f"graph pivot: {result.get('warnings')}"
        )


def _wrapper_literal(name: str) -> set[str]:
    """String members of a `Literal[...]` declared inside `register_tools`.

    The wrapper Literals are function-local, so they are read off the source
    rather than imported.
    """
    import ast
    import inspect
    import textwrap

    from multiomics_explorer.mcp_server.tools import register_tools

    tree = ast.parse(textwrap.dedent(inspect.getsource(register_tools)))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if name not in targets:
            continue
        return {
            n.value for n in ast.walk(node.value)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        }
    raise AssertionError(f"{name} not found in register_tools")


@pytest.mark.kg
class TestLiteralsAgreeWithTheVocabulary:
    """Wrapper-layer `Literal[...]` value sets are a discoverability aid, not
    a second source of truth. They must agree with the graph exactly, or a KG
    vocabulary change silently rejects a valid value at the wrapper."""

    def test_call_class_literal_matches_the_vocabulary(self, conn):
        literal_values = _wrapper_literal("_CALL_CLASSES")
        row = _vocab_row(conn, "Gene_has_merops_family", "call_class")
        assert row is not None, "call_class vocabulary node is missing"
        assert literal_values == set(row["values"]), (
            f"_CALL_CLASSES Literal {sorted(literal_values)} disagrees with "
            f"Gene_has_merops_family.call_class {sorted(row['values'])}."
        )

    def test_interpro_type_literal_matches_the_vocabulary(self, conn):
        literal_values = _wrapper_literal("_INTERPRO_TYPES")
        row = _vocab_row(conn, "InterproEntry", "interpro_type")
        assert row is not None, "interpro_type vocabulary node is missing"
        assert literal_values == set(row["values"]), (
            f"_INTERPRO_TYPES Literal {sorted(literal_values)} disagrees with "
            f"InterproEntry.interpro_type {sorted(row['values'])}."
        )
