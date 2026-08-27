"""ONTOLOGY_CONFIG registry invariants (annotation-trust surface, PR 3a).

`ONTOLOGY_CONFIG` is the single registry for every column, filter, facet,
bridge and validation the ontology builders perform. These tests pin the
registry shape and cross-check every prop the registry names against the
captured KG schema baseline (`multiomics_explorer/config/schema_baseline.yaml`).

No Neo4j needed — the baseline yaml is the schema oracle.
"""

from pathlib import Path

import pytest
import yaml

from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG

# --- schema baseline oracle -------------------------------------------------

_BASELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "multiomics_explorer" / "config" / "schema_baseline.yaml"
)


@pytest.fixture(scope="module")
def baseline():
    with _BASELINE_PATH.open() as fh:
        return yaml.safe_load(fh)["schema"]


def _node_props(baseline, label):
    return set(baseline["nodes"].get(label, {}).get("properties", {}))


def _rel_props(baseline, rel_type):
    return set(baseline["relationships"].get(rel_type, {}).get("properties", {}))


def _verbose_edge_pairs(cfg):
    """Normalize `verbose_edge` entries to (neo4j_prop, output_column).

    A bare string means column == prop; a 2-tuple/list means (prop, column).
    PSORTb / SignalP are the only renaming entries today
    (`score` -> `localization_score`, `probability` ->
    `signal_peptide_probability`).
    """
    pairs = []
    for entry in cfg.get("verbose_edge", []) or []:
        if isinstance(entry, str):
            pairs.append((entry, entry))
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            pairs.append((entry[0], entry[1]))
        elif isinstance(entry, dict):
            pairs.append((entry["prop"], entry.get("column", entry["prop"])))
        else:  # pragma: no cover - guard
            raise AssertionError(f"unrecognised verbose_edge entry: {entry!r}")
    return pairs


# --- registry membership ----------------------------------------------------

NEW_ONTOLOGIES = ["interpro", "ncbifam", "merops"]

EXISTING_14 = [
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam",
    "brite", "tcdb", "cazy",
    "subcellular_localization", "signal_peptide_type",
]

ALL_17 = EXISTING_14 + NEW_ONTOLOGIES


class TestRegistryMembership:
    def test_all_ontologies_is_existing_14_plus_3_appended(self):
        assert ALL_ONTOLOGIES == ALL_17

    def test_all_ontologies_has_17_entries(self):
        assert len(ALL_ONTOLOGIES) == 17

    def test_config_covers_exactly_all_ontologies(self):
        assert set(ONTOLOGY_CONFIG) == set(ALL_ONTOLOGIES)

    @pytest.mark.parametrize("key", NEW_ONTOLOGIES)
    def test_new_key_present(self, key):
        assert key in ONTOLOGY_CONFIG


class TestNewOntologyRows:
    """Label / gene_rel / hierarchy / fulltext index for the 3 new keys."""

    def test_interpro_core_fields(self):
        cfg = ONTOLOGY_CONFIG["interpro"]
        assert cfg["label"] == "InterproEntry"
        assert cfg["gene_rel"] == "Gene_has_interpro_entry"
        assert cfg["hierarchy_rels"] == ["Interpro_entry_is_a_interpro_entry"]
        assert cfg["fulltext_index"] == "interproEntryFullText"

    def test_ncbifam_core_fields(self):
        cfg = ONTOLOGY_CONFIG["ncbifam"]
        assert cfg["label"] == "NcbifamFamily"
        assert cfg["gene_rel"] == "Gene_has_ncbifam_family"
        assert cfg["hierarchy_rels"] == []
        assert cfg["fulltext_index"] == "ncbifamFamilyFullText"

    def test_merops_core_fields(self):
        cfg = ONTOLOGY_CONFIG["merops"]
        assert cfg["label"] == "MeropsFamily"
        assert cfg["gene_rel"] == "Gene_has_merops_family"
        assert cfg["hierarchy_rels"] == ["Merops_family_is_a_merops_family"]
        assert cfg["fulltext_index"] == "meropsFamilyFullText"

    @pytest.mark.parametrize("key", NEW_ONTOLOGIES)
    def test_new_keys_carry_no_bridge_or_parent_label(self, key):
        cfg = ONTOLOGY_CONFIG[key]
        assert "bridge" not in cfg
        assert "parent_label" not in cfg


# --- trust axes -------------------------------------------------------------

EXPECTED_TRUST_AXES = {
    "go_bp": ["sources", "evidence", "evidence_score"],
    "go_mf": ["sources", "evidence", "evidence_score"],
    "go_cc": ["sources", "evidence", "evidence_score"],
    "ec": ["sources", "evidence", "evidence_score"],
    "pfam": ["sources", "evidence", "evidence_score"],
    "cazy": ["sources", "evidence", "evidence_score"],
    "kegg": ["sources", "evidence"],
    "cog_category": ["sources", "evidence"],
    "cyanorak_role": ["sources", "evidence"],
    "tigr_role": ["sources", "evidence"],
    # BRITE binds `r` on the Gene_has_kegg_ko edge, so it carries KEGG's axes.
    "brite": ["sources", "evidence"],
    "tcdb": ["sources", "evidence", "evidence_score", "tier"],
    "merops": ["sources", "evidence", "evidence_score", "tier"],
    "interpro": ["sources", "evidence"],
    "ncbifam": ["sources", "evidence"],
    "subcellular_localization": [],
    "signal_peptide_type": [],
}


class TestTrustAxes:
    @pytest.mark.parametrize("key", ALL_17)
    def test_trust_axes_match_spec_table(self, key):
        from multiomics_explorer.kg.queries_lib import ontology_trust_axes
        assert ontology_trust_axes(key) == EXPECTED_TRUST_AXES[key]

    def test_rank_prop_is_not_an_axis(self):
        """`rank_prop` lives inside `trust` but is a sort key, not an axis."""
        from multiomics_explorer.kg.queries_lib import ontology_trust_axes
        assert "rank_prop" not in ontology_trust_axes("tcdb")
        assert "rank_prop" not in ontology_trust_axes("merops")

    def test_tcdb_rank_prop_is_evidence_score(self):
        assert ONTOLOGY_CONFIG["tcdb"]["trust"]["rank_prop"] == "evidence_score"

    def test_merops_rank_prop_is_confidence_score(self):
        assert ONTOLOGY_CONFIG["merops"]["trust"]["rank_prop"] == "confidence_score"

    @pytest.mark.parametrize(
        "key", ["subcellular_localization", "signal_peptide_type"])
    def test_psortb_signalp_carry_no_trust(self, key):
        cfg = ONTOLOGY_CONFIG[key]
        assert cfg.get("trust") in (None, {})

    @pytest.mark.parametrize("key", ALL_17)
    def test_rank_prop_is_declared_elsewhere_in_the_entry(self, key):
        """Design section 2 invariant: rank_prop in trust union verbose_edge."""
        cfg = ONTOLOGY_CONFIG[key]
        rank_prop = (cfg.get("trust") or {}).get("rank_prop")
        if rank_prop is None:
            pytest.skip(f"{key} declares no rank_prop")
        trust_props = {
            v for k, v in (cfg.get("trust") or {}).items() if k != "rank_prop"
        }
        verbose_props = {p for p, _ in _verbose_edge_pairs(cfg)}
        assert rank_prop in trust_props | verbose_props


# --- compact_edge / facet ---------------------------------------------------


class TestCompactEdgeAndFacet:
    def test_merops_compact_edge_is_call_class_with_warn_value(self):
        cfg = ONTOLOGY_CONFIG["merops"]
        assert "call_class" in cfg["compact_edge"]
        entry = cfg["compact_edge"]["call_class"]
        assert entry["prop"] == "call_class"
        assert "nonpeptidase_homolog" in entry["warn_values"]

    @pytest.mark.parametrize("key", [k for k in ALL_17 if k != "merops"])
    def test_only_merops_declares_compact_edge(self, key):
        assert ONTOLOGY_CONFIG[key].get("compact_edge") in (None, {})

    def test_brite_facet_is_tree(self):
        assert ONTOLOGY_CONFIG["brite"]["facet"] == {
            "prop": "tree", "param": "tree"}

    def test_interpro_facet_is_interpro_type(self):
        assert ONTOLOGY_CONFIG["interpro"]["facet"] == {
            "prop": "interpro_type", "param": "interpro_type"}

    @pytest.mark.parametrize(
        "key", [k for k in ALL_17 if k not in ("brite", "interpro")])
    def test_no_other_ontology_declares_a_facet(self, key):
        assert ONTOLOGY_CONFIG[key].get("facet") is None


# --- verbose_edge (native detail) -------------------------------------------

EXPECTED_VERBOSE_EDGE_PROPS = {
    "tcdb": ["confidence_score", "source_agreement", "pfam_support", "go_support",
             "identity", "qcov", "evalue", "consensus_n", "attachment_depth"],
    "merops": ["confidence_score", "pfam_support", "best_hit_kind", "identity",
               "qcov", "evalue", "consensus_n", "best_hit_id"],
    "interpro": ["libraries", "evalue_library", "evalue", "match_count",
                 "start", "end"],
    "ncbifam": ["evalue", "bit_score", "start", "end"],
    "subcellular_localization": ["score"],
    "signal_peptide_type": ["probability", "cleavage_site", "cleavage_probability"],
}


class TestVerboseEdge:
    @pytest.mark.parametrize("key", sorted(EXPECTED_VERBOSE_EDGE_PROPS))
    def test_verbose_edge_props_match_spec_table(self, key):
        props = [p for p, _ in _verbose_edge_pairs(ONTOLOGY_CONFIG[key])]
        assert props == EXPECTED_VERBOSE_EDGE_PROPS[key]

    @pytest.mark.parametrize(
        "key", [k for k in ALL_17 if k not in EXPECTED_VERBOSE_EDGE_PROPS])
    def test_ontologies_without_native_detail_declare_none(self, key):
        assert ONTOLOGY_CONFIG[key].get("verbose_edge") in (None, [])


# --- term side --------------------------------------------------------------

EXPECTED_TERM_VERBOSE = {
    "tcdb": ["superfamily", "metabolite_count"],
    "merops": ["family_class", "catalytic_type", "peptidase_gene_count"],
    "ncbifam": ["family_type", "gene_symbol"],
}


class TestTermSide:
    @pytest.mark.parametrize("key", ALL_17)
    def test_term_compact_is_gene_count_and_organism_count(self, key):
        assert ONTOLOGY_CONFIG[key]["term_compact"] == [
            "gene_count", "organism_count"]

    @pytest.mark.parametrize("key", sorted(EXPECTED_TERM_VERBOSE))
    def test_term_verbose_matches_spec_table(self, key):
        assert ONTOLOGY_CONFIG[key]["term_verbose"] == EXPECTED_TERM_VERBOSE[key]

    @pytest.mark.parametrize(
        "key", [k for k in ALL_17 if k not in EXPECTED_TERM_VERBOSE])
    def test_term_verbose_empty_elsewhere(self, key):
        assert ONTOLOGY_CONFIG[key].get("term_verbose") in (None, [])

    @pytest.mark.parametrize("key", ALL_17)
    def test_term_details_verbose_is_star(self, key):
        assert ONTOLOGY_CONFIG[key]["term_details_verbose"] == "*"

    @pytest.mark.parametrize("key", ALL_17)
    def test_term_details_compact_covers_term_compact_and_verbose(self, key):
        """Design section 2 invariant: term_details_compact superset."""
        cfg = ONTOLOGY_CONFIG[key]
        declared = set(cfg["term_details_compact"] or [])
        # term_compact (gene_count / organism_count) is emitted unconditionally
        # by the term-details row, so the union it must cover is term_verbose.
        missing = set(cfg.get("term_verbose") or []) - declared - set(
            cfg["term_compact"])
        assert not missing, (
            f"{key}: term_details_compact misses {sorted(missing)}")

    def test_merops_term_details_compact_matches_spec(self):
        assert ONTOLOGY_CONFIG["merops"]["term_details_compact"] == [
            "merops_id", "family_class", "catalytic_type", "peptidase_gene_count",
            "peptidase_organism_count", "direct_gene_count", "member_count",
            "cleavage_summary", "cleavage_p1_residues", "known_cleavage_count",
        ]

    def test_interpro_term_details_compact_matches_spec(self):
        assert ONTOLOGY_CONFIG["interpro"]["term_details_compact"] == [
            "interpro_id", "interpro_type", "direct_gene_count", "member_count",
        ]

    def test_ncbifam_term_details_compact_matches_spec(self):
        assert ONTOLOGY_CONFIG["ncbifam"]["term_details_compact"] == [
            "ncbifam_id", "family_type", "gene_symbol",
        ]


# --- bridges ----------------------------------------------------------------

VALID_LINK_KINDS = {"composition", "membership", "router"}

EXPECTED_BRIDGES = {
    "kegg": [("Kegg_term_in_brite_category", "brite", "membership")],
    "pfam": [("Pfam_in_interpro_entry", "interpro", "membership")],
    "tcdb": [
        ("Tcdb_family_has_pfam_domain", "pfam", "composition"),
        ("Tcdb_family_involved_in_biological_process", "go_bp", "composition"),
        ("Tcdb_family_enables_molecular_function", "go_mf", "composition"),
        ("Tcdb_family_located_in_cellular_component", "go_cc", "composition"),
    ],
    "merops": [("Merops_family_has_pfam_domain", "pfam", "composition")],
    "interpro": [
        ("Interpro_entry_related_to_ec_number", "ec", "router"),
        ("Interpro_entry_related_to_cazy_family", "cazy", "router"),
    ],
    "ncbifam": [("Ncbifam_family_in_interpro_entry", "interpro", "membership")],
}


class TestBridges:
    @pytest.mark.parametrize("key", sorted(EXPECTED_BRIDGES))
    def test_bridges_out_matches_spec_table(self, key):
        got = [tuple(b) for b in ONTOLOGY_CONFIG[key]["bridges_out"]]
        assert got == EXPECTED_BRIDGES[key]

    @pytest.mark.parametrize(
        "key", [k for k in ALL_17 if k not in EXPECTED_BRIDGES])
    def test_no_bridges_elsewhere(self, key):
        assert ONTOLOGY_CONFIG[key].get("bridges_out") in (None, [])

    @pytest.mark.parametrize("key", ALL_17)
    def test_bridge_targets_are_known_config_keys(self, key):
        for rel, target, kind in ONTOLOGY_CONFIG[key].get("bridges_out") or []:
            assert target in ONTOLOGY_CONFIG, (
                f"{key}: bridge {rel} points at unknown ontology {target!r}")
            assert kind in VALID_LINK_KINDS, (
                f"{key}: bridge {rel} has unknown link_kind {kind!r}")

    @pytest.mark.parametrize("key", ALL_17)
    def test_bridge_rel_types_exist_in_baseline(self, key, baseline):
        for rel, _target, _kind in ONTOLOGY_CONFIG[key].get("bridges_out") or []:
            assert rel in baseline["relationships"], (
                f"{key}: bridge rel {rel!r} absent from schema baseline")


# --- schema-baseline cross-check -------------------------------------------


class TestConfigPropsExistInSchemaBaseline:
    """Every prop the registry names must exist on the live-KG baseline.

    Covers the props the PR 3a builders actually project or filter on:
    trust axes, compact_edge, verbose_edge (edge props on `gene_rel`) and
    facet / term_compact / term_verbose (node props on `label`).
    """

    @pytest.mark.parametrize("key", ALL_17)
    def test_trust_props_exist_on_gene_rel(self, key, baseline):
        cfg = ONTOLOGY_CONFIG[key]
        props = _rel_props(baseline, cfg["gene_rel"])
        for axis, prop in (cfg.get("trust") or {}).items():
            assert prop in props, (
                f"{key}: trust axis {axis!r} -> {prop!r} not on "
                f"{cfg['gene_rel']}")

    @pytest.mark.parametrize("key", ALL_17)
    def test_compact_edge_props_exist_on_gene_rel(self, key, baseline):
        cfg = ONTOLOGY_CONFIG[key]
        props = _rel_props(baseline, cfg["gene_rel"])
        for col, entry in (cfg.get("compact_edge") or {}).items():
            assert entry["prop"] in props, (
                f"{key}: compact_edge {col!r} -> {entry['prop']!r} not on "
                f"{cfg['gene_rel']}")

    @pytest.mark.parametrize("key", ALL_17)
    def test_verbose_edge_props_exist_on_gene_rel(self, key, baseline):
        cfg = ONTOLOGY_CONFIG[key]
        props = _rel_props(baseline, cfg["gene_rel"])
        for prop, col in _verbose_edge_pairs(cfg):
            assert prop in props, (
                f"{key}: verbose_edge {col!r} -> {prop!r} not on "
                f"{cfg['gene_rel']}")

    @pytest.mark.parametrize("key", ALL_17)
    def test_facet_prop_exists_on_label(self, key, baseline):
        cfg = ONTOLOGY_CONFIG[key]
        facet = cfg.get("facet")
        if not facet:
            pytest.skip(f"{key} has no facet")
        assert facet["prop"] in _node_props(baseline, cfg["label"])

    @pytest.mark.parametrize("key", ALL_17)
    def test_term_compact_and_verbose_props_exist_on_label(self, key, baseline):
        cfg = ONTOLOGY_CONFIG[key]
        props = _node_props(baseline, cfg["label"])
        for prop in list(cfg["term_compact"]) + list(cfg.get("term_verbose") or []):
            assert prop in props, (
                f"{key}: term prop {prop!r} not on {cfg['label']}")

    @pytest.mark.parametrize("key", ALL_17)
    def test_gene_rel_and_label_exist_in_baseline(self, key, baseline):
        cfg = ONTOLOGY_CONFIG[key]
        assert cfg["label"] in baseline["nodes"]
        assert cfg["gene_rel"] in baseline["relationships"]

    @pytest.mark.parametrize("key", ALL_17)
    def test_hierarchy_rels_exist_in_baseline(self, key, baseline):
        for rel in ONTOLOGY_CONFIG[key]["hierarchy_rels"]:
            assert rel in baseline["relationships"], (
                f"{key}: hierarchy rel {rel!r} absent from schema baseline")


# --- ownership: config declares shape, ControlledVocabulary owns values -----

_VALUE_LIST_KEYS = {
    "values", "allowed_values", "evidence_values", "call_class_values",
    "interpro_types", "tier_values", "sources_values",
}


class TestConfigDeclaresNoValueLists:
    """Values / descriptions / ranges live in ControlledVocabulary, not here."""

    @pytest.mark.parametrize("key", ALL_17)
    def test_no_value_list_keys(self, key):
        offending = _VALUE_LIST_KEYS & set(ONTOLOGY_CONFIG[key])
        assert not offending, f"{key}: config declares value lists {offending}"


class TestSupersededRegistryKeysRemoved:
    """`edge_props` (PSORTb-era) is superseded by `trust` / `verbose_edge`."""

    @pytest.mark.parametrize("key", ALL_17)
    def test_edge_props_key_gone(self, key):
        assert "edge_props" not in ONTOLOGY_CONFIG[key]

    def test_api_edge_prop_cols_constant_deleted(self):
        from multiomics_explorer.api import functions as api
        assert not hasattr(api, "_EDGE_PROP_COLS")
