"""Drift tests: hardcoded constants vs live KG.

These tests detect when a KG rebuild introduces values that our
constants don't account for.  When a test fails:

  1. Update the constant in kg/constants.py (or queries_lib.py)
  2. Check if tool descriptions or validators in tools.py reference
     the old values and need updating
  3. Re-run the full test suite to catch downstream breakage

These are NOT fixture tests — do not "fix" by changing the assertions.
"""

import pytest

from multiomics_explorer.kg.constants import (
    MAX_SPECIFICITY_RANK,
    VALID_CLUSTER_TYPES,
    VALID_OMICS_TYPES,
    VALID_OG_SOURCES,
    VALID_TAXONOMIC_LEVELS,
)


pytestmark = pytest.mark.kg


def _drift_msg(name: str, location: str, expected: set, actual: set) -> str:
    """Format a helpful assertion message for drift failures."""
    missing = actual - expected
    extra = expected - actual
    lines = [f"{name} in {location} is out of sync with KG."]
    if missing:
        lines.append(f"  Missing from constant: {missing}")
    if extra:
        lines.append(f"  Extra in constant (not in KG): {extra}")
    lines.append(
        "  Update the constant, then check if tools.py descriptions"
        " or validators also need updating."
    )
    return "\n".join(lines)


class TestOrthologGroupConstants:
    """VALID_OG_SOURCES, VALID_TAXONOMIC_LEVELS, MAX_SPECIFICITY_RANK."""

    def test_valid_og_sources_match_kg(self, run_query):
        results = run_query(
            "MATCH (og:OrthologGroup) RETURN DISTINCT og.source AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == VALID_OG_SOURCES, _drift_msg(
            "VALID_OG_SOURCES", "kg/constants.py", VALID_OG_SOURCES, actual
        )

    def test_valid_taxonomic_levels_match_kg(self, run_query):
        results = run_query(
            "MATCH (og:OrthologGroup) "
            "RETURN DISTINCT og.taxonomic_level AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == VALID_TAXONOMIC_LEVELS, _drift_msg(
            "VALID_TAXONOMIC_LEVELS",
            "kg/constants.py",
            VALID_TAXONOMIC_LEVELS,
            actual,
        )

    def test_max_specificity_rank_match_kg(self, run_query):
        results = run_query(
            "MATCH (og:OrthologGroup) "
            "RETURN max(og.specificity_rank) AS val"
        )
        actual = results[0]["val"]
        assert actual == MAX_SPECIFICITY_RANK, (
            f"MAX_SPECIFICITY_RANK in kg/constants.py is {MAX_SPECIFICITY_RANK}"
            f" but KG max is {actual}."
            " Update the constant."
        )


class TestExperimentConstants:
    """VALID_CLUSTER_TYPES, VALID_OMICS_TYPES."""

    def test_valid_cluster_types_match_kg(self, run_query):
        results = run_query(
            "MATCH (ca:ClusteringAnalysis) "
            "RETURN DISTINCT ca.cluster_type AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == VALID_CLUSTER_TYPES, _drift_msg(
            "VALID_CLUSTER_TYPES",
            "kg/constants.py",
            VALID_CLUSTER_TYPES,
            actual,
        )

    def test_valid_omics_types_match_kg(self, run_query):
        results = run_query(
            "MATCH (e:Experiment) RETURN DISTINCT e.omics_type AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == VALID_OMICS_TYPES, _drift_msg(
            "VALID_OMICS_TYPES",
            "kg/constants.py",
            VALID_OMICS_TYPES,
            actual,
        )


class TestExpressionConstants:
    """expression_status Literal on ExpressionRow (nested in tools.py)."""

    # The Literal values are hardcoded here because ExpressionRow is a
    # nested class inside a tool function and not importable.  If the
    # Literal in tools.py:1503 changes, update this set too.
    EXPECTED_STATUSES = {"significant_up", "significant_down", "not_significant"}

    def test_expression_status_match_kg(self, run_query):
        results = run_query(
            "MATCH ()-[r:Changes_expression_of]->() "
            "RETURN DISTINCT r.expression_status AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == self.EXPECTED_STATUSES, _drift_msg(
            "ExpressionRow.expression_status Literal",
            "mcp_server/tools.py:1503",
            self.EXPECTED_STATUSES,
            actual,
        )


from multiomics_explorer.kg.constants import EXPECTED_KG_SHAPE
from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG


class TestOntologyConfig:
    """Verify every ONTOLOGY_CONFIG entry maps to real KG schema elements."""

    @pytest.mark.parametrize("key", sorted(ONTOLOGY_CONFIG.keys()))
    def test_node_label_exists(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        label = cfg["label"]
        results = run_query(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
        cnt = results[0]["cnt"]
        assert cnt > 0, (
            f"ONTOLOGY_CONFIG['{key}']['label'] = '{label}' — "
            f"no nodes with this label found in KG. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )

    @pytest.mark.parametrize("key", sorted(ONTOLOGY_CONFIG.keys()))
    def test_gene_relationship_exists(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        rel = cfg["gene_rel"]
        results = run_query(
            f"MATCH ()-[r:`{rel}`]->() RETURN count(r) AS cnt LIMIT 1"
        )
        cnt = results[0]["cnt"]
        assert cnt > 0, (
            f"ONTOLOGY_CONFIG['{key}']['gene_rel'] = '{rel}' — "
            f"no relationships of this type found in KG. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )

    @pytest.mark.parametrize(
        "key",
        [k for k in sorted(ONTOLOGY_CONFIG.keys()) if ONTOLOGY_CONFIG[k]["hierarchy_rels"]],
    )
    def test_hierarchy_relationships_exist(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        for rel in cfg["hierarchy_rels"]:
            results = run_query(
                f"MATCH ()-[r:`{rel}`]->() RETURN count(r) AS cnt LIMIT 1"
            )
            cnt = results[0]["cnt"]
            assert cnt > 0, (
                f"ONTOLOGY_CONFIG['{key}']['hierarchy_rels'] contains '{rel}' — "
                f"no relationships of this type found in KG. "
                f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
            )

    @pytest.mark.parametrize("key", sorted(ONTOLOGY_CONFIG.keys()))
    def test_fulltext_index_queryable(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        idx = cfg["fulltext_index"]
        # A minimal query — just needs to not error
        results = run_query(
            f"CALL db.index.fulltext.queryNodes('{idx}', 'test') "
            f"YIELD node RETURN count(node) AS cnt"
        )
        # No assertion on count — zero results is fine, the index just needs to exist
        assert results is not None, (
            f"ONTOLOGY_CONFIG['{key}']['fulltext_index'] = '{idx}' — "
            f"fulltext index query failed. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )

    @pytest.mark.parametrize(
        "key",
        [k for k in sorted(ONTOLOGY_CONFIG.keys()) if "parent_label" in ONTOLOGY_CONFIG[k]],
    )
    def test_parent_label_exists(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        label = cfg["parent_label"]
        results = run_query(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
        cnt = results[0]["cnt"]
        assert cnt > 0, (
            f"ONTOLOGY_CONFIG['{key}']['parent_label'] = '{label}' — "
            f"no nodes with this label found in KG. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )

    @pytest.mark.parametrize(
        "key",
        [k for k in sorted(ONTOLOGY_CONFIG.keys()) if "parent_fulltext_index" in ONTOLOGY_CONFIG[k]],
    )
    def test_parent_fulltext_index_queryable(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        idx = cfg["parent_fulltext_index"]
        results = run_query(
            f"CALL db.index.fulltext.queryNodes('{idx}', 'test') "
            f"YIELD node RETURN count(node) AS cnt"
        )
        assert results is not None, (
            f"ONTOLOGY_CONFIG['{key}']['parent_fulltext_index'] = '{idx}' — "
            f"fulltext index query failed. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )


# ---------------------------------------------------------------------------
# EXPECTED_KG_SHAPE drift tests
# ---------------------------------------------------------------------------


class TestExpectedKGShape:
    """Verify every entry in EXPECTED_KG_SHAPE is satisfied by the live KG.

    These tests catch schema drift: renamed/dropped node labels, missing
    relationship types, and stale Schema_info property expectations.

    Failure remediation: update EXPECTED_KG_SHAPE in kg/constants.py
    (drop the dead entry, or add the renamed one).
    """

    def test_expected_kg_shape_labels_present_in_kg(self, run_query):
        """Every node label in EXPECTED_KG_SHAPE['required_node_labels']
        must exist in the live KG. Drift catches: KG renamed a label, KG
        dropped a label we expected.

        Failure remediation: update EXPECTED_KG_SHAPE in kg/constants.py
        (drop the dead label, or add the renamed one)."""
        results = run_query("CALL db.labels() YIELD label RETURN collect(label) AS labels")
        live_labels = set(results[0]["labels"])
        expected = set(EXPECTED_KG_SHAPE["required_node_labels"])
        missing = expected - live_labels
        assert not missing, (
            f"EXPECTED_KG_SHAPE['required_node_labels'] in kg/constants.py "
            f"is out of sync with the live KG.\n  Missing from db.labels(): {missing}\n"
            f"  Update kg/constants.py to drop the dead labels, or rebuild the KG."
        )

    def test_expected_kg_shape_relationship_types_present_in_kg(self, run_query):
        """Every relationship type in EXPECTED_KG_SHAPE must exist."""
        results = run_query(
            "CALL db.relationshipTypes() YIELD relationshipType "
            "RETURN collect(relationshipType) AS rt"
        )
        live_rts = set(results[0]["rt"])
        expected = set(EXPECTED_KG_SHAPE["required_relationship_types"])
        missing = expected - live_rts
        assert not missing, (
            f"EXPECTED_KG_SHAPE['required_relationship_types'] in kg/constants.py "
            f"is out of sync with the live KG.\n  Missing from db.relationshipTypes(): {missing}\n"
            f"  Update kg/constants.py to drop the dead rel types, or rebuild the KG."
        )

    def test_expected_kg_shape_schema_info_props_present_in_kg(self, run_query):
        """Every property in EXPECTED_KG_SHAPE['schema_info_required_props']
        must exist as a non-null Schema_info property in the live KG."""
        results = run_query(
            "MATCH (s:Schema_info {id: 'schema_info'}) RETURN s { .* } AS si"
        )
        assert results, "Schema_info node not found in live KG."
        si = results[0]["si"]
        expected = set(EXPECTED_KG_SHAPE["schema_info_required_props"])
        missing = {p for p in expected if si.get(p) is None}
        assert not missing, (
            f"EXPECTED_KG_SHAPE['schema_info_required_props'] in kg/constants.py "
            f"is out of sync with the live KG.\n  Missing or null on Schema_info: {missing}\n"
            f"  Update kg/constants.py to drop the dead props, or rebuild the KG."
        )
