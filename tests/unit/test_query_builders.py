"""Unit tests for query builder functions — no Neo4j needed.

Verifies Cypher structure and parameter correctness.
"""

import pytest

from multiomics_explorer.kg.constants import ALL_ONTOLOGIES, GO_ONTOLOGIES
from multiomics_explorer.kg.queries_lib import (
    ONTOLOGY_CONFIG,
    build_gene_existence_check,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_gene_ontology_terms,
    build_gene_ontology_terms_summary,
    build_gene_overview,
    build_gene_overview_summary,
    build_gene_stub,
    build_genes_by_function,
    build_genes_by_function_summary,
    build_gene_details,
    build_gene_details_summary,
    build_list_gene_categories,
    build_list_growth_phases,
    build_list_organisms,
    build_list_organisms_summary,
    build_list_publications,
    build_list_publications_summary,
    build_list_experiments,
    build_list_experiments_summary,
    build_resolve_gene,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_diagnostics,
    build_genes_by_homolog_group_summary,
    build_search_ontology,
    build_search_ontology_summary,
    build_differential_expression_by_gene,
    build_differential_expression_by_gene_summary_global,
    build_differential_expression_by_gene_summary_by_experiment,
    build_differential_expression_by_gene_summary_diagnostics,
    build_differential_expression_by_ortholog_group_check,
    build_differential_expression_by_ortholog_summary_global,
    build_differential_expression_by_ortholog_top_groups,
    build_differential_expression_by_ortholog_top_experiments,
    build_differential_expression_by_ortholog_results,
    build_differential_expression_by_ortholog_membership_counts,
    build_differential_expression_by_ortholog_diagnostics,
    build_resolve_organism_for_organism,
    build_resolve_organism_for_locus_tags,
    build_resolve_organism_for_experiments,
    build_gene_response_profile_envelope,
    build_gene_response_profile,
    build_ontology_landscape,
    build_ontology_expcov,
    build_ontology_experiment_check,
    build_ontology_organism_gene_count,
    build_gene_derived_metrics_summary,
    build_gene_derived_metrics,
    build_genes_by_numeric_metric_diagnostics,
    build_genes_by_numeric_metric_summary,
    build_genes_by_numeric_metric,
    build_genes_by_boolean_metric_diagnostics,
    build_genes_by_boolean_metric_summary,
    build_genes_by_boolean_metric,
    build_genes_by_categorical_metric_diagnostics,
    build_genes_by_categorical_metric_summary,
    build_genes_by_categorical_metric,
)
from multiomics_explorer.kg.queries_lib import _hierarchy_walk


class TestHierarchyWalk:
    def test_go_bp_up(self):
        frag = _hierarchy_walk("go_bp", direction="up")
        assert frag["leaf_label"] == "BiologicalProcess"
        assert frag["gene_rel"] == "Gene_involved_in_biological_process"
        assert "Biological_process_is_a_biological_process" in frag["rel_union"]
        assert "Biological_process_part_of_biological_process" in frag["rel_union"]
        # Up walk binds gene → leaf, then leaf → ancestor
        assert "(g:Gene {organism_name: $org})-[:Gene_involved_in_biological_process]->(leaf:BiologicalProcess)" in frag["bind_up"]
        assert "(leaf)-[:" in frag["walk_up"]
        assert "]->(t:BiologicalProcess)" in frag["walk_up"]

    def test_go_bp_down(self):
        frag = _hierarchy_walk("go_bp", direction="down")
        # Down walk: root matched first, then walk to descendants/leaves
        assert "(t:BiologicalProcess)<-[:" in frag["walk_down"]
        assert "]-(leaf:BiologicalProcess)" in frag["walk_down"]

    def test_flat_ontology_has_no_walk(self):
        frag = _hierarchy_walk("cog_category", direction="up")
        # Flat: t = leaf; walk_up is empty; bind goes directly to t
        assert frag["rel_union"] == ""
        assert frag["walk_up"] == ""
        assert "(g:Gene {organism_name: $org})-[:Gene_in_cog_category]->(t:CogFunctionalCategory)" in frag["bind_up"]

    def test_tigr_role_flat(self):
        frag = _hierarchy_walk("tigr_role", direction="up")
        assert frag["walk_up"] == ""
        assert frag["leaf_label"] == "TigrRole"

    def test_pfam_up_crosses_to_clan(self):
        frag = _hierarchy_walk("pfam", direction="up")
        # Pfam up: leaf=Pfam, walk via Pfam_in_pfam_clan *0..1, t can be Pfam or PfamClan
        assert "(leaf:Pfam)" in frag["bind_up"]
        assert "Pfam_in_pfam_clan" in frag["walk_up"]
        assert "*0..1" in frag["walk_up"]
        # target can be either label
        assert "t:Pfam OR t:PfamClan" in frag["walk_up"] or "t:PfamClan OR t:Pfam" in frag["walk_up"]

    def test_pfam_down_pfam_root(self):
        """Pfam root (level 1): no walk — t is the leaf."""
        frag = _hierarchy_walk("pfam", direction="down", root_label="Pfam")
        assert frag["walk_down"] == ""  # Pfam root has no Pfam descendants

    def test_pfam_down_pfamclan_root(self):
        """PfamClan root (level 0): walk down via Pfam_in_pfam_clan."""
        frag = _hierarchy_walk("pfam", direction="down", root_label="PfamClan")
        assert "(t:PfamClan)<-[:Pfam_in_pfam_clan]-(leaf:Pfam)" in frag["walk_down"]

    def test_kegg_single_label(self):
        frag = _hierarchy_walk("kegg", direction="up")
        assert frag["leaf_label"] == "KeggTerm"
        assert "Kegg_term_is_a_kegg_term" in frag["rel_union"]

    def test_unknown_ontology_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid ontology"):
            _hierarchy_walk("not_a_real_ontology", direction="up")

    def test_direction_required(self):
        import pytest
        with pytest.raises(ValueError, match="direction"):
            _hierarchy_walk("go_bp", direction="sideways")

    def test_brite_up_uses_bridge(self):
        frag = _hierarchy_walk("brite", direction="up")
        assert frag["leaf_label"] == "BriteCategory"
        assert frag["gene_rel"] == "Gene_has_kegg_ko"
        assert "Brite_category_is_a_brite_category" in frag["rel_union"]
        # 2-hop bind: Gene → KeggTerm → BriteCategory
        assert ":Gene_has_kegg_ko" in frag["bind_up"]
        assert ":KeggTerm" in frag["bind_up"]
        assert ":Kegg_term_in_brite_category" in frag["bind_up"]
        assert "(leaf:BriteCategory)" in frag["bind_up"]
        # Walk up within BriteCategory hierarchy
        assert "Brite_category_is_a_brite_category*0.." in frag["walk_up"]
        assert "(t:BriteCategory)" in frag["walk_up"]

    def test_brite_down_uses_bridge(self):
        frag = _hierarchy_walk("brite", direction="down")
        # Walk down: root → descendants within BriteCategory
        assert "(t:BriteCategory)<-[:Brite_category_is_a_brite_category*0..]-(leaf:BriteCategory)" in frag["walk_down"]

    def test_brite_bind_up_starts_with_standard_prefix(self):
        """bind_up must start with standard Gene prefix for expcov prefix-stripping."""
        frag = _hierarchy_walk("brite", direction="up")
        assert frag["bind_up"].startswith(
            "MATCH (g:Gene {organism_name: $org})"
        )


class TestOntologyConfigBrite:
    def test_brite_in_ontology_config(self):
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        assert "brite" in ONTOLOGY_CONFIG
        cfg = ONTOLOGY_CONFIG["brite"]
        assert cfg["label"] == "BriteCategory"
        assert cfg["gene_rel"] == "Gene_has_kegg_ko"
        assert cfg["hierarchy_rels"] == ["Brite_category_is_a_brite_category"]
        assert cfg["fulltext_index"] == "briteCategoryFullText"
        assert cfg["bridge"] == {
            "node_label": "KeggTerm",
            "edge": "Kegg_term_in_brite_category",
        }

    def test_brite_in_all_ontologies(self):
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert "brite" in ALL_ONTOLOGIES


class TestOntologyConfigTcdb:
    """TCDB ontology added to ONTOLOGY_CONFIG (Phase 2)."""

    def test_tcdb_in_ontology_config(self):
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        assert "tcdb" in ONTOLOGY_CONFIG
        cfg = ONTOLOGY_CONFIG["tcdb"]
        assert cfg["label"] == "TcdbFamily"
        assert cfg["gene_rel"] == "Gene_has_tcdb_family"
        assert cfg["hierarchy_rels"] == ["Tcdb_family_is_a_tcdb_family"]
        assert cfg["fulltext_index"] == "tcdbFamilyFullText"
        # No bridge (single-label tree ontology, like GO/EC/KEGG/CyanoRak)
        assert "bridge" not in cfg
        # No parent fields (only pfam has those)
        assert "parent_label" not in cfg
        assert "parent_fulltext_index" not in cfg

    def test_tcdb_in_all_ontologies(self):
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert "tcdb" in ALL_ONTOLOGIES

    def test_tcdb_appended_after_brite(self):
        """Order is load-bearing for regression-fixture determinism: tcdb
        must come after the existing 10 ontologies (after 'brite')."""
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert ALL_ONTOLOGIES.index("tcdb") > ALL_ONTOLOGIES.index("brite")


class TestOntologyConfigCazy:
    """CAZy ontology added to ONTOLOGY_CONFIG (Phase 2)."""

    def test_cazy_in_ontology_config(self):
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        assert "cazy" in ONTOLOGY_CONFIG
        cfg = ONTOLOGY_CONFIG["cazy"]
        assert cfg["label"] == "CazyFamily"
        assert cfg["gene_rel"] == "Gene_has_cazy_family"
        assert cfg["hierarchy_rels"] == ["Cazy_family_is_a_cazy_family"]
        assert cfg["fulltext_index"] == "cazyFamilyFullText"
        # No bridge (single-label tree ontology)
        assert "bridge" not in cfg
        # No parent fields
        assert "parent_label" not in cfg
        assert "parent_fulltext_index" not in cfg

    def test_cazy_in_all_ontologies(self):
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert "cazy" in ALL_ONTOLOGIES

    def test_cazy_appended_after_tcdb(self):
        """Order is load-bearing: cazy follows tcdb at the end of the list."""
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        assert ALL_ONTOLOGIES.index("cazy") > ALL_ONTOLOGIES.index("tcdb")


class TestHierarchyWalkTcdb:
    """_hierarchy_walk for tcdb routes through the single-label tree branch
    (the same branch GO/EC/KEGG/CyanoRak follow)."""

    def test_tcdb_up(self):
        frag = _hierarchy_walk("tcdb", direction="up")
        assert frag["leaf_label"] == "TcdbFamily"
        assert frag["gene_rel"] == "Gene_has_tcdb_family"
        assert frag["rel_union"] == "Tcdb_family_is_a_tcdb_family"
        # Bind: gene → leaf
        assert (
            "(g:Gene {organism_name: $org})-[:Gene_has_tcdb_family]->(leaf:TcdbFamily)"
            in frag["bind_up"]
        )
        # Walk up: leaf → ancestor at any level via *0..
        assert "Tcdb_family_is_a_tcdb_family*0.." in frag["walk_up"]
        assert "(t:TcdbFamily)" in frag["walk_up"]

    def test_tcdb_down(self):
        frag = _hierarchy_walk("tcdb", direction="down")
        assert frag["leaf_label"] == "TcdbFamily"
        assert frag["gene_rel"] == "Gene_has_tcdb_family"
        # Walk down: root → leaf
        assert (
            "(t:TcdbFamily)<-[:Tcdb_family_is_a_tcdb_family*0..]-(leaf:TcdbFamily)"
            in frag["walk_down"]
        )

    def test_tcdb_bind_up_starts_with_standard_prefix(self):
        """bind_up must start with standard Gene prefix (no bridge ontology)."""
        frag = _hierarchy_walk("tcdb", direction="up")
        assert frag["bind_up"].startswith(
            "MATCH (g:Gene {organism_name: $org})"
        )


class TestHierarchyWalkCazy:
    """_hierarchy_walk for cazy: same single-label tree branch."""

    def test_cazy_up(self):
        frag = _hierarchy_walk("cazy", direction="up")
        assert frag["leaf_label"] == "CazyFamily"
        assert frag["gene_rel"] == "Gene_has_cazy_family"
        assert frag["rel_union"] == "Cazy_family_is_a_cazy_family"
        assert (
            "(g:Gene {organism_name: $org})-[:Gene_has_cazy_family]->(leaf:CazyFamily)"
            in frag["bind_up"]
        )
        assert "Cazy_family_is_a_cazy_family*0.." in frag["walk_up"]
        assert "(t:CazyFamily)" in frag["walk_up"]

    def test_cazy_down(self):
        frag = _hierarchy_walk("cazy", direction="down")
        assert frag["leaf_label"] == "CazyFamily"
        assert (
            "(t:CazyFamily)<-[:Cazy_family_is_a_cazy_family*0..]-(leaf:CazyFamily)"
            in frag["walk_down"]
        )

    def test_cazy_bind_up_starts_with_standard_prefix(self):
        frag = _hierarchy_walk("cazy", direction="up")
        assert frag["bind_up"].startswith(
            "MATCH (g:Gene {organism_name: $org})"
        )


class TestBuildResolveGene:
    def test_basic(self):
        cypher, params = build_resolve_gene(identifier="PMM0001")
        assert "MATCH (g:Gene)" in cypher
        assert params["identifier"] == "PMM0001"
        assert params["organism"] is None

    def test_with_organism(self):
        cypher, params = build_resolve_gene(identifier="dnaN", organism="MED4")
        assert params["organism"] == "MED4"
        assert "toLower($organism)" in cypher
        assert "toLower(g.organism_name)" in cypher

    def test_organism_case_insensitive(self):
        """Organism filter uses toLower for case-insensitive matching."""
        cypher, params = build_resolve_gene(identifier="recF", organism="prochlorococcus")
        assert params["organism"] == "prochlorococcus"
        assert "toLower($organism)" in cypher

    def test_organism_multi_word_partial(self):
        """Multi-word organism like 'Alteromonas EZ55' uses ALL/split for word matching."""
        cypher, params = build_resolve_gene(identifier="recF", organism="Alteromonas EZ55")
        assert params["organism"] == "Alteromonas EZ55"
        assert "ALL(word IN split(" in cypher

    def test_returns_expected_columns(self):
        cypher, _ = build_resolve_gene(identifier="x")
        for col in ["locus_tag", "gene_name", "product", "organism_name"]:
            assert col in cypher

    def test_matches_all_identifiers(self):
        """Query checks all_identifiers list for alternate IDs (old locus tags, RefSeq IDs)."""
        cypher, _ = build_resolve_gene(identifier="x")
        assert "ANY(id IN g.all_identifiers WHERE toLower(id) = toLower($identifier))" in cypher

    def test_order_by_organism_then_locus_tag(self):
        cypher, _ = build_resolve_gene(identifier="x")
        assert "ORDER BY g.organism_name, g.locus_tag" in cypher

    def test_identifier_uses_tolower(self):
        """All three identifier match conditions use toLower for case-insensitive matching."""
        cypher, _ = build_resolve_gene(identifier="PMM0001")
        assert "toLower(g.locus_tag) = toLower($identifier)" in cypher
        assert "toLower(g.gene_name) = toLower($identifier)" in cypher
        assert "ANY(id IN g.all_identifiers WHERE toLower(id) = toLower($identifier))" in cypher


class TestBuildGenesByFunction:
    def test_no_filters(self):
        cypher, params = build_genes_by_function(search_text="DNA repair")
        assert "fulltext" in cypher.lower() or "geneFullText" in cypher
        assert params["search_text"] == "DNA repair"
        assert params["organism"] is None
        assert params["category"] is None
        assert params["min_quality"] == 0

    def test_organism_filter(self):
        """Organism filter uses toLower for case-insensitive matching."""
        cypher, params = build_genes_by_function(search_text="x", organism="prochlorococcus")
        assert params["organism"] == "prochlorococcus"
        assert "toLower($organism)" in cypher

    def test_category_filter(self):
        """When category is provided, it is passed as $category parameter."""
        cypher, params = build_genes_by_function(search_text="x", category="Photosynthesis")
        assert params["category"] == "Photosynthesis"
        assert "gene_category" in cypher
        assert "$category" in cypher

    def test_min_quality_filter(self):
        _, params = build_genes_by_function(search_text="x", min_quality=2)
        assert params["min_quality"] == 2

    def test_combined_filters(self):
        """All three filters (organism, category, min_quality) in WHERE."""
        cypher, params = build_genes_by_function(
            search_text="x", organism="MED4", category="Photosynthesis", min_quality=2,
        )
        assert "toLower($organism)" in cypher
        assert "$category" in cypher
        assert "$min_quality" in cypher
        assert params["organism"] == "MED4"
        assert params["category"] == "Photosynthesis"
        assert params["min_quality"] == 2

    def test_returns_expected_columns(self):
        """RETURN clause includes all compact columns."""
        cypher, _ = build_genes_by_function(search_text="x")
        for col in ["locus_tag", "gene_name", "product", "organism_name",
                     "gene_category", "annotation_quality", "score"]:
            assert col in cypher

    def test_order_by(self):
        """ORDER BY score DESC, g.locus_tag."""
        cypher, _ = build_genes_by_function(search_text="x")
        assert "ORDER BY score DESC, g.locus_tag" in cypher

    def test_verbose_false(self):
        """Compact mode excludes function_description and gene_summary."""
        cypher, _ = build_genes_by_function(search_text="x", verbose=False)
        assert "function_description" not in cypher
        assert "gene_summary" not in cypher

    def test_verbose_true(self):
        """Verbose mode includes function_description and gene_summary."""
        cypher, _ = build_genes_by_function(search_text="x", verbose=True)
        assert "function_description" in cypher
        assert "gene_summary" in cypher

    def test_limit_clause(self):
        """LIMIT is added when limit is provided."""
        cypher, params = build_genes_by_function(search_text="x", limit=50)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 50

    def test_limit_none(self):
        """No LIMIT when limit is None."""
        cypher, _ = build_genes_by_function(search_text="x", limit=None)
        assert "LIMIT" not in cypher

    def test_offset_emits_skip(self):
        cypher, params = build_genes_by_function(
            search_text="x", limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        # SKIP must come before LIMIT
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_genes_by_function(
            search_text="x", limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params


class TestBuildGenesByFunctionSummary:
    def test_no_filters(self):
        cypher, params = build_genes_by_function_summary(search_text="DNA repair")
        assert "geneFullText" in cypher
        assert params["search_text"] == "DNA repair"
        assert params["organism"] is None
        assert params["category"] is None

    def test_with_filters(self):
        """Filters are applied to the summary query."""
        cypher, params = build_genes_by_function_summary(
            search_text="x", organism="MED4", category="Photosynthesis", min_quality=2,
        )
        assert "toLower($organism)" in cypher
        assert params["organism"] == "MED4"
        assert params["category"] == "Photosynthesis"
        assert params["min_quality"] == 2

    def test_returns_total_search_hits_and_total_matching(self):
        """RETURN clause includes both total_search_hits and total_matching."""
        cypher, _ = build_genes_by_function_summary(search_text="x")
        assert "total_search_hits" in cypher
        assert "total_matching" in cypher

    def test_returns_breakdowns(self):
        """RETURN clause includes by_organism and by_category."""
        cypher, _ = build_genes_by_function_summary(search_text="x")
        assert "by_organism" in cypher
        assert "by_category" in cypher

    def test_returns_score_stats(self):
        """RETURN clause includes score_max and score_median."""
        cypher, _ = build_genes_by_function_summary(search_text="x")
        assert "score_max" in cypher
        assert "score_median" in cypher



class TestBuildGeneOverview:
    def test_returns_expected_columns(self):
        """UNWIND + MATCH, returns 11 compact columns, $locus_tags in params."""
        cypher, params = build_gene_overview(locus_tags=["PMM1428"])
        assert "UNWIND" in cypher
        assert "MATCH (g:Gene" in cypher
        assert params["locus_tags"] == ["PMM1428"]
        expected_columns = [
            "locus_tag", "gene_name", "product", "gene_category",
            "annotation_quality", "organism_name", "annotation_types",
            "expression_edge_count", "significant_up_count", "significant_down_count",
            "closest_ortholog_group_size", "closest_ortholog_genera",
            "cluster_membership_count", "cluster_types",
        ]
        for col in expected_columns:
            assert col in cypher, f"Missing column '{col}' in RETURN clause"

    def test_verbose_false(self):
        """Compact mode omits gene_summary, function_description, all_identifiers."""
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"], verbose=False)
        assert "gene_summary" not in cypher
        assert "function_description" not in cypher
        assert "all_identifiers" not in cypher

    def test_verbose_true(self):
        """Verbose mode includes gene_summary, function_description, all_identifiers."""
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"], verbose=True)
        assert "gene_summary" in cypher
        assert "function_description" in cypher
        assert "all_identifiers" in cypher

    def test_limit_clause(self):
        """limit=10 adds LIMIT $limit to Cypher."""
        cypher, params = build_gene_overview(locus_tags=["PMM1428"], limit=10)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        """limit=None omits LIMIT clause."""
        cypher, params = build_gene_overview(locus_tags=["PMM1428"], limit=None)
        assert "LIMIT" not in cypher
        assert "limit" not in params

    def test_order_by(self):
        """Results ordered by locus_tag."""
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"])
        assert "ORDER BY g.locus_tag" in cypher

    def test_offset_emits_skip(self):
        cypher, params = build_gene_overview(
            locus_tags=["PMM1428"], limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_gene_overview(
            locus_tags=["PMM1428"], limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_compact_includes_per_kind_dm_counts(self):
        """Compact mode always includes per-kind DM count columns."""
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"], verbose=False)
        assert "boolean_metric_count" in cypher
        assert "numeric_metric_count" in cypher
        assert "categorical_metric_count" in cypher

    def test_compact_omits_types_observed_and_compartments(self):
        """Compact mode omits per-kind types lists and compartments_observed."""
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"], verbose=False)
        assert "numeric_metric_types_observed" not in cypher
        assert "boolean_metric_types_observed" not in cypher
        assert "categorical_metric_types_observed" not in cypher
        assert "compartments_observed" not in cypher

    def test_verbose_includes_types_observed_and_compartments(self):
        """Verbose mode adds per-kind types lists and compartments_observed."""
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"], verbose=True)
        assert "numeric_metric_types_observed" in cypher
        assert "boolean_metric_types_observed" in cypher
        assert "categorical_metric_types_observed" in cypher
        assert "compartments_observed" in cypher

    def test_uses_post_d8_prop_names(self):
        """Uses post-D8 KG names (boolean_metric_count, not classifier_flag_count)."""
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"])
        assert "classifier_flag" not in cypher
        assert "classifier_label" not in cypher


class TestBuildGeneOverviewSummary:
    def test_returns_summary_keys(self):
        """Summary query uses OPTIONAL MATCH, frequencies, flatten."""
        cypher, params = build_gene_overview_summary(locus_tags=["PMM1428"])
        assert "OPTIONAL MATCH" in cypher
        assert "apoc.coll.frequencies" in cypher
        assert "apoc.coll.flatten" in cypher
        assert "total_matching" in cypher
        assert "by_organism" in cypher
        assert "by_category" in cypher
        assert "by_annotation_type" in cypher
        assert "has_expression" in cypher
        assert "has_significant_expression" in cypher
        assert "has_orthologs" in cypher
        assert "has_clusters" in cypher
        assert "not_found" in cypher
        assert params["locus_tags"] == ["PMM1428"]

    def test_not_found_logic(self):
        """Summary query detects not_found via OPTIONAL MATCH + CASE WHEN g IS NULL."""
        cypher, _ = build_gene_overview_summary(locus_tags=["PMM1428", "FAKE"])
        assert "OPTIONAL MATCH" in cypher
        assert "CASE WHEN g IS NULL" in cypher

    def test_has_derived_metrics_in_summary(self):
        """Summary emits has_derived_metrics using post-D8 arithmetic."""
        cypher, _ = build_gene_overview_summary(locus_tags=["PMM1428"])
        assert "has_derived_metrics" in cypher
        assert "boolean_metric_count" in cypher
        assert "numeric_metric_count" in cypher
        assert "categorical_metric_count" in cypher

    def test_summary_uses_post_d8_prop_names(self):
        """Summary uses post-D8 prop names (no classifier_* references)."""
        cypher, _ = build_gene_overview_summary(locus_tags=["PMM1428"])
        assert "classifier_flag" not in cypher
        assert "classifier_label" not in cypher


class TestBuildGeneDetails:
    def test_batch_locus_tags(self):
        """Batch query with locus_tags list, g {.*} in RETURN."""
        cypher, params = build_gene_details(locus_tags=["PMM0001", "PMM0002"])
        assert params["locus_tags"] == ["PMM0001", "PMM0002"]
        assert "UNWIND $locus_tags" in cypher
        assert "g {.*}" in cypher
        assert "ORDER BY" in cypher

    def test_limit(self):
        cypher, params = build_gene_details(locus_tags=["PMM0001"], limit=10)
        assert params["limit"] == 10
        assert "LIMIT $limit" in cypher

    def test_no_limit(self):
        cypher, params = build_gene_details(locus_tags=["PMM0001"])
        assert "LIMIT" not in cypher

    def test_build_get_gene_details_retired(self):
        """build_get_gene_details no longer importable from queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_get_gene_details")

    def test_build_get_gene_details_homologs_deleted(self):
        """build_get_gene_details_homologs no longer importable from queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_get_gene_details_homologs")

    def test_offset_emits_skip(self):
        cypher, params = build_gene_details(
            locus_tags=["PMM0001"], limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_gene_details(
            locus_tags=["PMM0001"], limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params


class TestBuildGeneDetailsSummary:
    def test_summary_returns_total_and_not_found(self):
        cypher, params = build_gene_details_summary(locus_tags=["PMM0001"])
        assert params["locus_tags"] == ["PMM0001"]
        assert "total_matching" in cypher
        assert "not_found" in cypher
        assert "OPTIONAL MATCH" in cypher


class TestRemovedExpressionBuilders:
    """Verify old expression builders are removed (schema migration B1)."""

    def test_build_query_expression_removed(self):
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_query_expression")

    def test_build_compare_conditions_removed(self):
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_compare_conditions")

    def test_build_list_condition_types_removed(self):
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_list_condition_types")

    def test_direct_expr_rels_constant_removed(self):
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "DIRECT_EXPR_RELS")


class TestBuildGeneHomologs:
    def test_no_filters(self):
        """No filters: UNWIND + MATCH pattern, no WHERE clause."""
        cypher, params = build_gene_homologs(locus_tags=["PMM0845"])
        assert "UNWIND $locus_tags" in cypher
        assert "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)" in cypher
        assert "WHERE" not in cypher
        assert params["locus_tags"] == ["PMM0845"]

    def test_returns_compact_columns(self):
        """Compact mode (verbose=False) returns 8 columns."""
        cypher, _ = build_gene_homologs(locus_tags=["PMM0845"])
        for col in [
            "locus_tag", "organism_name", "group_id",
            "consensus_gene_name", "consensus_product",
            "taxonomic_level", "source", "specificity_rank",
        ]:
            assert col in cypher

    def test_order_by(self):
        """ORDER BY locus_tag, specificity_rank, source."""
        cypher, _ = build_gene_homologs(locus_tags=["x"])
        assert "ORDER BY g.locus_tag, og.specificity_rank, og.source" in cypher

    def test_source_filter(self):
        cypher, params = build_gene_homologs(locus_tags=["x"], source="cyanorak")
        assert "og.source = $source" in cypher
        assert params["source"] == "cyanorak"

    def test_taxonomic_level_filter(self):
        cypher, params = build_gene_homologs(locus_tags=["x"], taxonomic_level="Bacteria")
        assert "og.taxonomic_level = $level" in cypher
        assert params["level"] == "Bacteria"

    def test_max_specificity_rank_filter(self):
        cypher, params = build_gene_homologs(locus_tags=["x"], max_specificity_rank=1)
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["max_rank"] == 1

    def test_combined_filters(self):
        """All three filters (source, taxonomic_level, max_specificity_rank) in WHERE."""
        cypher, params = build_gene_homologs(
            locus_tags=["x"], source="eggnog", taxonomic_level="Bacteria",
            max_specificity_rank=3,
        )
        assert "og.source = $source" in cypher
        assert "og.taxonomic_level = $level" in cypher
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["source"] == "eggnog"
        assert params["level"] == "Bacteria"
        assert params["max_rank"] == 3

    def test_no_filter_when_all_none(self):
        """No WHERE clause when all filters are None."""
        cypher, params = build_gene_homologs(locus_tags=["x"])
        assert "WHERE" not in cypher
        assert params == {"locus_tags": ["x"]}

    def test_verbose_false_no_extra_columns(self):
        """Compact mode excludes verbose-only columns."""
        cypher, _ = build_gene_homologs(locus_tags=["x"], verbose=False)
        assert "member_count" not in cypher
        assert "organism_count" not in cypher
        assert "genera" not in cypher
        assert "has_cross_genus_members" not in cypher
        assert "description" not in cypher
        assert "functional_description" not in cypher

    def test_verbose_true_includes_extra_columns(self):
        """Verbose mode adds member_count, organism_count, genera, has_cross_genus_members, description, functional_description."""
        cypher, _ = build_gene_homologs(locus_tags=["x"], verbose=True)
        assert "og.member_count AS member_count" in cypher
        assert "og.organism_count AS organism_count" in cypher
        assert "og.genera AS genera" in cypher
        assert "og.has_cross_genus_members AS has_cross_genus_members" in cypher
        assert "og.description AS description" in cypher
        assert "og.functional_description AS functional_description" in cypher

    def test_specificity_rank_always_in_compact(self):
        """specificity_rank is returned in compact mode (not verbose-only)."""
        cypher, _ = build_gene_homologs(locus_tags=["x"], verbose=False)
        assert "og.specificity_rank AS specificity_rank" in cypher

    def test_group_id_uses_og_id(self):
        """group_id maps to og.id (prefixed), not og.name."""
        cypher, _ = build_gene_homologs(locus_tags=["x"])
        assert "og.id AS group_id" in cypher

    def test_limit_clause(self):
        """LIMIT is added when limit is provided."""
        cypher, params = build_gene_homologs(locus_tags=["x"], limit=50)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 50

    def test_limit_none(self):
        """No LIMIT when limit is None."""
        cypher, _ = build_gene_homologs(locus_tags=["x"], limit=None)
        assert "LIMIT" not in cypher

    def test_gene_in_ortholog_group(self):
        """Uses Gene_in_ortholog_group relationship and OrthologGroup label."""
        cypher, _ = build_gene_homologs(locus_tags=["x"])
        assert "Gene_in_ortholog_group" in cypher
        assert "OrthologGroup" in cypher

    @pytest.mark.parametrize("rank", [0, 1, 2, 3])
    def test_max_specificity_rank_boundary_values(self, rank):
        """Each valid rank value (0-3) produces correct WHERE clause."""
        cypher, params = build_gene_homologs(locus_tags=["x"], max_specificity_rank=rank)
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["max_rank"] == rank

    def test_multiple_locus_tags(self):
        """Accepts multiple locus tags."""
        cypher, params = build_gene_homologs(locus_tags=["PMM0845", "PMM1428"])
        assert params["locus_tags"] == ["PMM0845", "PMM1428"]

    def test_offset_emits_skip(self):
        cypher, params = build_gene_homologs(
            locus_tags=["PMM0845"], limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_gene_homologs(
            locus_tags=["PMM0845"], limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_cyanorak_roles_filter(self):
        cypher, params = build_gene_homologs(
            locus_tags=["PMM0845"], cyanorak_roles=["cyanorak.role:G.3"])
        assert "Og_has_cyanorak_role" in cypher
        assert "CyanorakRole" in cypher
        assert "$cyanorak_roles" in cypher
        assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]

    def test_cog_categories_filter(self):
        cypher, params = build_gene_homologs(
            locus_tags=["PMM0845"], cog_categories=["cog.category:J"])
        assert "Og_in_cog_category" in cypher
        assert "CogFunctionalCategory" in cypher
        assert "$cog_categories" in cypher
        assert params["cog_categories"] == ["cog.category:J"]

    def test_both_ontology_filters(self):
        cypher, params = build_gene_homologs(
            locus_tags=["PMM0845"],
            cyanorak_roles=["cyanorak.role:G.3"],
            cog_categories=["cog.category:J"],
        )
        assert "Og_has_cyanorak_role" in cypher
        assert "Og_in_cog_category" in cypher
        assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]
        assert params["cog_categories"] == ["cog.category:J"]

    def test_ontology_filter_none_no_clause(self):
        cypher, params = build_gene_homologs(locus_tags=["PMM0845"])
        assert "Og_has_cyanorak_role" not in cypher
        assert "Og_in_cog_category" not in cypher
        assert "cyanorak_roles" not in params
        assert "cog_categories" not in params

    def test_verbose_includes_ontology_columns(self):
        cypher, _ = build_gene_homologs(locus_tags=["PMM0845"], verbose=True)
        assert "cyanorak_roles" in cypher
        assert "cog_categories" in cypher
        assert "Og_has_cyanorak_role" in cypher
        assert "Og_in_cog_category" in cypher
        assert "OPTIONAL MATCH" in cypher

    def test_verbose_false_excludes_ontology_columns(self):
        cypher, _ = build_gene_homologs(locus_tags=["PMM0845"], verbose=False)
        assert "cyanorak_roles" not in cypher
        assert "cog_categories" not in cypher


class TestBuildGeneHomologsSummary:
    def test_returns_summary_columns(self):
        """Returns total_matching, by_organism, by_source, not_found, no_groups."""
        cypher, params = build_gene_homologs_summary(locus_tags=["PMM0845"])
        for col in ["total_matching", "by_organism", "by_source", "not_found", "no_groups"]:
            assert col in cypher
        assert params["locus_tags"] == ["PMM0845"]

    def test_uses_optional_match(self):
        """Summary uses OPTIONAL MATCH for gene and OG lookups."""
        cypher, _ = build_gene_homologs_summary(locus_tags=["x"])
        assert "OPTIONAL MATCH" in cypher

    def test_has_unwind(self):
        """Has UNWIND $locus_tags."""
        cypher, _ = build_gene_homologs_summary(locus_tags=["x"])
        assert "UNWIND $locus_tags" in cypher

    def test_source_filter_forwarded(self):
        """Source filter is forwarded to WHERE clause."""
        cypher, params = build_gene_homologs_summary(locus_tags=["x"], source="cyanorak")
        assert "og.source = $source" in cypher
        assert params["source"] == "cyanorak"

    def test_taxonomic_level_filter_forwarded(self):
        """Taxonomic level filter is forwarded to WHERE clause."""
        cypher, params = build_gene_homologs_summary(locus_tags=["x"], taxonomic_level="Bacteria")
        assert "og.taxonomic_level = $level" in cypher
        assert params["level"] == "Bacteria"

    def test_max_specificity_rank_filter_forwarded(self):
        """Max specificity rank filter is forwarded to WHERE clause."""
        cypher, params = build_gene_homologs_summary(locus_tags=["x"], max_specificity_rank=2)
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["max_rank"] == 2

    def test_no_filter_when_all_none(self):
        """No OG filter WHERE clause when all filters are None."""
        cypher, params = build_gene_homologs_summary(locus_tags=["x"])
        # No og.source / og.taxonomic_level / og.specificity_rank conditions
        assert "og.source" not in cypher
        assert "og.taxonomic_level" not in cypher
        assert "og.specificity_rank" not in cypher
        assert params == {"locus_tags": ["x"]}

    def test_cyanorak_roles_filter_forwarded(self):
        cypher, params = build_gene_homologs_summary(
            locus_tags=["x"], cyanorak_roles=["cyanorak.role:G.3"])
        assert "Og_has_cyanorak_role" in cypher
        assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]

    def test_cog_categories_filter_forwarded(self):
        cypher, params = build_gene_homologs_summary(
            locus_tags=["x"], cog_categories=["cog.category:J"])
        assert "Og_in_cog_category" in cypher
        assert params["cog_categories"] == ["cog.category:J"]

    def test_combined_filters(self):
        """All three filters appear in WHERE."""
        cypher, params = build_gene_homologs_summary(
            locus_tags=["x"], source="eggnog", taxonomic_level="Bacteria",
            max_specificity_rank=3,
        )
        assert "og.source = $source" in cypher
        assert "og.taxonomic_level = $level" in cypher
        assert "og.specificity_rank <= $max_rank" in cypher

    def test_summary_includes_top_ontology_breakdowns(self):
        cypher, _ = build_gene_homologs_summary(locus_tags=["PMM0845"])
        assert "top_cyanorak_roles" in cypher
        assert "top_cog_categories" in cypher
        assert "Og_has_cyanorak_role" in cypher
        assert "Og_in_cog_category" in cypher


class TestBuildGetHomologsOldRemoved:
    def test_old_build_get_homologs_no_longer_exists(self):
        """Old build_get_homologs function should not exist in queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_get_homologs")

    def test_old_build_homolog_expression_no_longer_exists(self):
        """Old build_homolog_expression function should not exist in queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_homolog_expression")

    def test_old_build_get_homologs_groups_no_longer_exists(self):
        """Old build_get_homologs_groups function should not exist in queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_get_homologs_groups")

    def test_old_build_get_homologs_members_no_longer_exists(self):
        """Old build_get_homologs_members function should not exist in queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_get_homologs_members")


class TestBuildListGeneCategories:
    def test_cypher_structure(self):
        cypher, params = build_list_gene_categories()
        assert "MATCH (g:Gene)" in cypher
        assert "gene_category" in cypher
        assert "category" in cypher
        assert "gene_count" in cypher
        assert "ORDER BY gene_count DESC" in cypher

    def test_no_params(self):
        _, params = build_list_gene_categories()
        assert params == {}


class TestBuildListBriteTrees:
    def test_returns_tree_and_tree_code_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_brite_trees
        cypher, params = build_list_brite_trees()
        assert "b.tree AS tree" in cypher
        assert "b.tree_code AS tree_code" in cypher
        assert "count(*) AS term_count" in cypher
        assert "ORDER BY b.tree" in cypher
        assert params == {}


class TestBuildListMetricTypes:
    def test_returns_value_and_count(self):
        from multiomics_explorer.kg.queries_lib import build_list_metric_types
        cypher, params = build_list_metric_types()
        assert "MATCH (dm:DerivedMetric)" in cypher
        assert "dm.metric_type AS value" in cypher
        assert "count(*) AS count" in cypher
        assert "ORDER BY count DESC" in cypher
        assert params == {}


class TestBuildListValueKinds:
    def test_returns_value_and_count(self):
        from multiomics_explorer.kg.queries_lib import build_list_value_kinds
        cypher, params = build_list_value_kinds()
        assert "dm.value_kind AS value" in cypher
        assert "count(*) AS count" in cypher
        assert params == {}


class TestBuildListCompartments:
    def test_sources_from_experiment_not_derived_metric(self):
        """D7: Experiment.compartment is the source-of-truth (wet-lab fraction)."""
        from multiomics_explorer.kg.queries_lib import build_list_compartments
        cypher, params = build_list_compartments()
        assert "MATCH (e:Experiment)" in cypher
        assert "e.compartment AS value" in cypher
        assert "DerivedMetric" not in cypher
        assert params == {}


class TestBuildListOrganisms:
    def test_cypher_structure(self):
        cypher, params = build_list_organisms()
        assert "MATCH (o:OrganismTaxon)" in cypher
        # Precomputed stats — no joins
        assert "OPTIONAL MATCH" not in cypher

    def test_returns_expected_columns(self):
        """Compact mode returns 11 columns from precomputed properties."""
        cypher, _ = build_list_organisms()
        for col in [
            "organism_name", "genus", "species", "strain", "clade",
            "ncbi_taxon_id", "gene_count", "publication_count",
            "experiment_count", "treatment_types", "omics_types",
        ]:
            assert col in cypher

    def test_reads_precomputed_props(self):
        """All stats read from node properties, no joins."""
        cypher, _ = build_list_organisms()
        assert "o.gene_count AS gene_count" in cypher
        assert "o.publication_count AS publication_count" in cypher
        assert "o.experiment_count AS experiment_count" in cypher

    def test_verbose_false(self):
        """Compact mode excludes taxonomy hierarchy columns."""
        cypher, _ = build_list_organisms(verbose=False)
        for col in ["family", "order", "tax_class", "phylum", "kingdom",
                     "superkingdom", "lineage"]:
            assert col not in cypher

    def test_verbose_true(self):
        """Verbose mode adds taxonomy hierarchy columns."""
        cypher, _ = build_list_organisms(verbose=True)
        for col in ["family", "order", "tax_class", "phylum", "kingdom",
                     "superkingdom", "lineage"]:
            assert col in cypher

    def test_default_params(self):
        _, params = build_list_organisms()
        assert params == {"organism_names_lc": None}

    def test_ordered_by_genus_and_name(self):
        cypher, _ = build_list_organisms()
        assert "ORDER BY o.genus, o.preferred_name" in cypher

    def test_returns_organism_type(self):
        cypher, _ = build_list_organisms()
        assert "o.organism_type AS organism_type" in cypher

    def test_returns_reference_fields(self):
        cypher, _ = build_list_organisms()
        assert "o.reference_database AS reference_database" in cypher
        assert "o.reference_proteome AS reference_proteome" in cypher

    def test_filter_clause_present(self):
        """WHERE gates the filter via $organism_names_lc IS NULL OR ..."""
        cypher, _ = build_list_organisms()
        assert "$organism_names_lc IS NULL" in cypher
        assert "toLower(o.preferred_name) IN $organism_names_lc" in cypher

    def test_filter_param_passthrough(self):
        """Lowercased input list is forwarded verbatim as a Cypher param."""
        names = ["prochlorococcus med4", "prochlorococcus mit9301"]
        _, params = build_list_organisms(organism_names_lc=names)
        assert params == {"organism_names_lc": names}

    def test_compact_returns_dm_rollup_fields(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms
        cypher, _ = build_list_organisms()
        assert "coalesce(o.derived_metric_count, 0) AS derived_metric_count" in cypher
        assert "coalesce(o.derived_metric_value_kinds, []) AS derived_metric_value_kinds" in cypher
        assert "coalesce(o.compartments, []) AS compartments" in cypher

    def test_verbose_adds_dm_extras(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms
        cypher, _ = build_list_organisms(verbose=True)
        assert "coalesce(o.derived_metric_gene_count, 0) AS derived_metric_gene_count" in cypher
        assert "coalesce(o.derived_metric_types, []) AS derived_metric_types" in cypher

    def test_compartment_filter_param(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms
        cypher, params = build_list_organisms(compartment="vesicle")
        assert "$compartment IN coalesce(o.compartments, [])" in cypher
        assert params["compartment"] == "vesicle"

    def test_compact_returns_chemistry_rollups(self):
        """Chemistry rollups (reaction_count, metabolite_count) are surfaced
        as compact RETURN columns, coalesced to 0 for organisms without
        chemistry coverage."""
        from multiomics_explorer.kg.queries_lib import build_list_organisms
        cypher, _ = build_list_organisms()
        assert "coalesce(o.reaction_count, 0) AS reaction_count" in cypher
        assert "coalesce(o.metabolite_count, 0) AS metabolite_count" in cypher


class TestBuildListOrganismsCapability:
    """Small-projection builder used by api/list_organisms in summary mode
    so the by_metabolic_capability rollup doesn't drag the full detail
    builder along."""

    def test_returns_only_three_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms_capability
        cypher, _ = build_list_organisms_capability()
        assert "o.preferred_name AS organism_name" in cypher
        assert "coalesce(o.reaction_count, 0) AS reaction_count" in cypher
        assert "coalesce(o.metabolite_count, 0) AS metabolite_count" in cypher
        # Stays small — no verbose / DM / cluster / reference columns
        for absent in ("lineage", "derived_metric_count", "cluster_count",
                        "reference_database", "treatment_types"):
            assert absent not in cypher

    def test_organism_names_filter_clause(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms_capability
        cypher, params = build_list_organisms_capability(
            organism_names_lc=["prochlorococcus med4"],
        )
        assert "$organism_names_lc IS NULL" in cypher
        assert "toLower(o.preferred_name) IN $organism_names_lc" in cypher
        assert params["organism_names_lc"] == ["prochlorococcus med4"]

    def test_compartment_filter_param(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms_capability
        cypher, params = build_list_organisms_capability(compartment="vesicle")
        assert "$compartment IN coalesce(o.compartments, [])" in cypher
        assert params["compartment"] == "vesicle"

    def test_ordered_by_genus_and_name(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms_capability
        cypher, _ = build_list_organisms_capability()
        assert "ORDER BY o.genus, o.preferred_name" in cypher


class TestBuildListOrganismsSummary:
    def test_returns_count(self):
        cypher, params = build_list_organisms_summary()
        assert "MATCH (o:OrganismTaxon)" in cypher
        assert "total_entries" in cypher
        # No-filter call — organism_names_lc=None is still a param.
        assert params == {"organism_names_lc": None}

    def test_summary_returns_rollup_keys(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms_summary
        cypher, _ = build_list_organisms_summary()
        assert "by_value_kind" in cypher
        assert "by_metric_type" in cypher
        assert "by_compartment" in cypher

    def test_summary_compartment_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms_summary
        cypher, params = build_list_organisms_summary(compartment="vesicle")
        assert "$compartment IN coalesce(o.compartments, [])" in cypher
        assert params["compartment"] == "vesicle"

    def test_summary_total_matching(self):
        from multiomics_explorer.kg.queries_lib import build_list_organisms_summary
        cypher, _ = build_list_organisms_summary()
        assert "total_matching" in cypher


class TestOntologyConfig:
    def test_all_keys_present(self):
        assert set(ONTOLOGY_CONFIG.keys()) == {
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam",
            "brite", "tcdb", "cazy",
        }

    def test_required_fields_present(self):
        for key, cfg in ONTOLOGY_CONFIG.items():
            assert "label" in cfg, f"{key} missing 'label'"
            assert "gene_rel" in cfg, f"{key} missing 'gene_rel'"
            assert "hierarchy_rels" in cfg, f"{key} missing 'hierarchy_rels'"
            assert "fulltext_index" in cfg, f"{key} missing 'fulltext_index'"

    def test_no_gene_connects_to_level(self):
        """gene_connects_to_level was removed — graph structure enforces KEGG's ko-leaf rule."""
        for key, cfg in ONTOLOGY_CONFIG.items():
            assert "gene_connects_to_level" not in cfg, (
                f"{key} should not have 'gene_connects_to_level' (removed)"
            )

    def test_pfam_has_parent_fields(self):
        """Pfam config has parent_label and parent_fulltext_index."""
        cfg = ONTOLOGY_CONFIG["pfam"]
        assert cfg["label"] == "Pfam"
        assert cfg["gene_rel"] == "Gene_has_pfam"
        assert cfg["hierarchy_rels"] == ["Pfam_in_pfam_clan"]
        assert cfg["fulltext_index"] == "pfamFullText"
        assert cfg["parent_label"] == "PfamClan"
        assert cfg["parent_fulltext_index"] == "pfamClanFullText"

    def test_only_pfam_has_parent_fields(self):
        """Only pfam has parent_label and parent_fulltext_index."""
        for key, cfg in ONTOLOGY_CONFIG.items():
            if key == "pfam":
                assert "parent_label" in cfg
                assert "parent_fulltext_index" in cfg
            else:
                assert "parent_label" not in cfg, (
                    f"{key} should not have 'parent_label'"
                )
                assert "parent_fulltext_index" not in cfg, (
                    f"{key} should not have 'parent_fulltext_index'"
                )


class TestBuildSearchOntology:
    @pytest.mark.parametrize("ontology,expected_index", [
        ("go_bp", "biologicalProcessFullText"),
        ("go_mf", "molecularFunctionFullText"),
        ("go_cc", "cellularComponentFullText"),
        ("ec", "ecNumberFullText"),
        ("kegg", "keggFullText"),
        ("cog_category", "cogCategoryFullText"),
        ("cyanorak_role", "cyanorakRoleFullText"),
        ("tigr_role", "tigrRoleFullText"),
        ("pfam", "pfamFullText"),
        ("tcdb", "tcdbFamilyFullText"),
        ("cazy", "cazyFamilyFullText"),
    ])
    def test_correct_fulltext_index(self, ontology, expected_index):
        cypher, _ = build_search_ontology(ontology=ontology, search_text="test")
        assert f"'{expected_index}'" in cypher

    def test_returns_id_name_score_columns(self):
        cypher, _ = build_search_ontology(ontology="go_bp", search_text="test")
        for col in ["id", "name", "score"]:
            assert col in cypher

    def test_invalid_ontology_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_search_ontology(ontology="invalid", search_text="test")

    def test_search_text_passed_as_parameter(self):
        cypher, params = build_search_ontology(ontology="go_bp", search_text="replication")
        assert params["search_text"] == "replication"
        assert "$search_text" in cypher
        assert "replication" not in cypher

    def test_pfam_union_query(self):
        cypher, _ = build_search_ontology(ontology="pfam", search_text="polymerase")
        assert "CALL {" in cypher
        assert "UNION ALL" in cypher
        assert "'pfamFullText'" in cypher
        assert "'pfamClanFullText'" in cypher

    def test_non_pfam_no_union(self):
        for ontology in ["go_bp", "go_mf", "go_cc", "ec", "kegg",
                         "cog_category", "cyanorak_role", "tigr_role",
                         "tcdb", "cazy"]:
            cypher, _ = build_search_ontology(ontology=ontology, search_text="test")
            assert "UNION ALL" not in cypher

    def test_limit_clause(self):
        cypher, params = build_search_ontology(ontology="go_bp", search_text="test", limit=10)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        cypher, params = build_search_ontology(ontology="go_bp", search_text="test")
        assert "LIMIT" not in cypher
        assert "limit" not in params

    def test_order_by_score_desc(self):
        cypher, _ = build_search_ontology(ontology="go_bp", search_text="test")
        assert "ORDER BY score DESC" in cypher

    def test_offset_emits_skip(self):
        cypher, params = build_search_ontology(
            ontology="go_bp", search_text="test", limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_search_ontology(
            ontology="go_bp", search_text="test", limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_returns_level_column(self):
        cypher, _ = build_search_ontology(ontology="go_bp", search_text="test")
        assert "t.level AS level" in cypher

    def test_returns_tree_columns(self):
        cypher, _ = build_search_ontology(ontology="brite", search_text="test")
        assert "t.tree AS tree" in cypher
        assert "t.tree_code AS tree_code" in cypher

    def test_level_filter_adds_where_clause(self):
        cypher, params = build_search_ontology(
            ontology="go_bp", search_text="test", level=2,
        )
        assert "t.level = $level" in cypher
        assert params["level"] == 2

    def test_tree_filter_adds_where_clause(self):
        cypher, params = build_search_ontology(
            ontology="brite", search_text="test", tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"

    def test_tree_filter_with_non_brite_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_search_ontology(
                ontology="go_bp", search_text="test", tree="transporters",
            )

    def test_pfam_union_level_filter_inside_branches(self):
        cypher, params = build_search_ontology(
            ontology="pfam", search_text="test", level=1,
        )
        # Level filter must appear inside each UNION branch
        assert cypher.count("t.level = $level") == 2
        assert params["level"] == 1


class TestBuildSearchOntologySummaryLevelTree:
    def test_level_filter(self):
        cypher, params = build_search_ontology_summary(
            ontology="go_bp", search_text="test", level=2,
        )
        assert "t.level = $level" in cypher
        assert params["level"] == 2

    def test_tree_filter(self):
        cypher, params = build_search_ontology_summary(
            ontology="brite", search_text="test", tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"

    def test_tree_non_brite_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_search_ontology_summary(
                ontology="go_bp", search_text="test", tree="x",
            )


class TestBuildSearchOntologySummary:
    def test_returns_summary_keys(self):
        cypher, _ = build_search_ontology_summary(ontology="go_bp", search_text="test")
        assert "total_entries" in cypher
        assert "total_matching" in cypher
        assert "score_max" in cypher
        assert "score_median" in cypher

    @pytest.mark.parametrize("ontology,expected_index", [
        ("go_bp", "biologicalProcessFullText"),
        ("kegg", "keggFullText"),
        ("pfam", "pfamFullText"),
    ])
    def test_correct_fulltext_index(self, ontology, expected_index):
        cypher, _ = build_search_ontology_summary(ontology=ontology, search_text="test")
        assert f"'{expected_index}'" in cypher

    def test_pfam_union_query(self):
        cypher, _ = build_search_ontology_summary(ontology="pfam", search_text="test")
        assert "UNION ALL" in cypher
        assert "pfam_count" in cypher
        assert "clan_count" in cypher

    def test_label_count_for_total_entries(self):
        cypher, _ = build_search_ontology_summary(ontology="go_bp", search_text="test")
        assert "BiologicalProcess" in cypher
        assert "total_entries" in cypher

    def test_invalid_ontology_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_search_ontology_summary(ontology="invalid", search_text="test")

    def test_search_text_passed_as_parameter(self):
        cypher, params = build_search_ontology_summary(ontology="go_bp", search_text="replication")
        assert params["search_text"] == "replication"
        assert "$search_text" in cypher


class TestBuildGenesByOntologyValidate:
    def test_single_label_ontology(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_validate,
        )
        cypher, params = build_genes_by_ontology_validate(
            term_ids=["go:0006260", "go:0006412"],
            ontology="go_bp",
            level=3,
        )
        assert params == {
            "term_ids": ["go:0006260", "go:0006412"],
            "expected_labels": ["BiologicalProcess"],
            "level": 3,
        }
        assert "UNWIND $term_ids AS tid" in cypher
        assert "OPTIONAL MATCH (t {id: tid})" in cypher
        # Guards all 10 label options
        assert "t:BiologicalProcess" in cypher
        assert "t:PfamClan" in cypher
        assert "ANY(L IN $expected_labels WHERE L IN labels(t))" in cypher
        assert "matched_label" in cypher

    def test_pfam_accepts_both_labels(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_validate,
        )
        _, params = build_genes_by_ontology_validate(
            term_ids=["pfam:PF00005", "pfam.clan:CL0023"],
            ontology="pfam",
            level=None,
        )
        assert params["expected_labels"] == ["Pfam", "PfamClan"]
        assert params["level"] is None

    def test_no_level_means_level_filter_skipped(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_validate,
        )
        cypher, params = build_genes_by_ontology_validate(
            term_ids=["go:0006260"],
            ontology="go_bp",
            level=None,
        )
        # Level check is conditional on $level — expression must guard on NULL
        assert "$level IS NOT NULL AND t.level <> $level" in cypher
        assert params["level"] is None

    def test_unknown_ontology_raises(self):
        import pytest
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_validate,
        )
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_genes_by_ontology_validate(
                term_ids=["x"], ontology="nope", level=0,
            )


class TestBuildGenesByOntologyDetail:
    def test_mode1_term_ids_only_walks_down(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, params = build_genes_by_ontology_detail(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            term_ids=["go:0006260"],
            level=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert params["term_ids"] == ["go:0006260"]
        assert params["org"] == "Prochlorococcus MED4"
        assert params["min_gene_set_size"] == 5
        assert params["max_gene_set_size"] == 500
        # Mode 1: walk DOWN from each input term
        assert "UNWIND $term_ids AS input_tid" in cypher
        assert "(t:BiologicalProcess {id: input_tid})" in cypher
        assert "<-[:" in cypher  # walk direction
        assert "(leaf:BiologicalProcess)" in cypher
        # Size filter
        assert "size(term_genes) >= $min_gene_set_size" in cypher
        assert "size(term_genes) <= $max_gene_set_size" in cypher
        # Row return
        assert "g.locus_tag AS locus_tag" in cypher
        assert "t.id AS term_id" in cypher
        assert "t.level AS level" in cypher
        # Verbose fields omitted by default
        assert "function_description" not in cypher
        assert "level_is_best_effort" not in cypher

    def test_mode2_level_only_walks_up(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, params = build_genes_by_ontology_detail(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert params["level"] == 1
        assert "$term_ids" not in cypher  # no term_ids clause
        # Mode 2: bind gene → leaf, walk leaf → ancestor
        assert "(g:Gene {organism_name: $org})-[:Gene_involved_in_biological_process]->(leaf:BiologicalProcess)" in cypher
        assert "(leaf)-[:" in cypher
        assert "]->(t:BiologicalProcess)" in cypher
        assert "WHERE t.level = $level" in cypher

    def test_mode3_level_and_term_ids(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="cyanorak_role",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=["cyanorak.role:A.1"],
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        # Mode 3: same as Mode 2 but with term_ids scope
        assert "WHERE t.level = $level AND t.id IN $term_ids" in cypher

    def test_verbose_adds_columns(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
            verbose=True,
        )
        assert "g.function_description AS function_description" in cypher
        assert "t.level_is_best_effort IS NOT NULL AS level_is_best_effort" in cypher

    def test_limit_and_offset(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, params = build_genes_by_ontology_detail(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
            limit=100,
            offset=50,
        )
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 100
        assert params["offset"] == 50

    def test_order_by_stable(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert "ORDER BY t.id, g.locus_tag" in cypher

    def test_no_mode_raises(self):
        import pytest
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        with pytest.raises(ValueError, match="level.*term_ids"):
            build_genes_by_ontology_detail(
                ontology="go_bp",
                organism="MED4",
                level=None,
                term_ids=None,
                min_gene_set_size=5,
                max_gene_set_size=500,
            )

    def test_flat_ontology_mode2(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="cog_category",
            organism="Prochlorococcus MED4",
            level=0,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        # Flat: t = leaf; no walk between leaf and t
        assert "(g:Gene {organism_name: $org})-[:Gene_in_cog_category]->(t:CogFunctionalCategory)" in cypher
        # No explicit leaf→t walk
        assert "(leaf)-[:" not in cypher

    def test_returns_tree_columns(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="brite", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
        )
        assert "t.tree AS tree" in cypher
        assert "t.tree_code AS tree_code" in cypher

    def test_tree_filter(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, params = build_genes_by_ontology_detail(
            ontology="brite", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
            tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"

    def test_tree_non_brite_raises(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_genes_by_ontology_detail(
                ontology="go_bp", organism="Test Org",
                level=2, min_gene_set_size=5, max_gene_set_size=500,
                tree="x",
            )


class TestBuildGenesByOntologyPerTerm:
    def test_mode2_returns_per_term_aggregate(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, params = build_genes_by_ontology_per_term(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert params["level"] == 1
        assert params["org"] == "Prochlorococcus MED4"
        # Returns per-term aggregate
        assert "t.id AS term_id" in cypher
        assert "t.name AS term_name" in cypher
        assert "t.level AS level" in cypher
        assert "t.level_is_best_effort IS NOT NULL AS best_effort" in cypher
        assert "size(gene_rows) AS n_genes" in cypher
        assert "apoc.coll.frequencies" in cypher
        assert "AS cat_freqs" in cypher
        assert "ORDER BY t.id" in cypher
        # Pagination NOT applied to summary queries
        assert "SKIP" not in cypher
        assert "LIMIT" not in cypher

    def test_mode1_term_ids(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, params = build_genes_by_ontology_per_term(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=None,
            term_ids=["go:0006260"],
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert params["term_ids"] == ["go:0006260"]
        assert "UNWIND $term_ids AS input_tid" in cypher

    def test_mode3_level_and_term_ids(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, _ = build_genes_by_ontology_per_term(
            ontology="cyanorak_role",
            organism="MED4",
            level=1,
            term_ids=["cyanorak.role:A.1"],
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert "t.level = $level" in cypher
        assert "t.id IN $term_ids" in cypher

    def test_pfam_mode1(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, _ = build_genes_by_ontology_per_term(
            ontology="pfam",
            organism="Prochlorococcus MED4",
            level=None,
            term_ids=["pfam:PF00005"],
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert "(tp:Pfam {id: input_tid})" in cypher
        assert "coalesce(tp, tc) AS t" in cypher

    def test_flat_ontology_mode2(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, _ = build_genes_by_ontology_per_term(
            ontology="tigr_role",
            organism="Prochlorococcus MED4",
            level=0,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        # Flat ontology: t = leaf, no walk
        assert "(g:Gene {organism_name: $org})-[:Gene_has_tigr_role]->(t:TigrRole)" in cypher
        assert "(leaf)-[:" not in cypher


class TestBuildGenesByOntologyPerGene:
    def test_mode2_per_gene_shape(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_gene,
        )
        cypher, _ = build_genes_by_ontology_per_gene(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert "g.locus_tag AS locus_tag" in cypher
        assert "coalesce(g.gene_category, 'Unknown') AS gene_category" in cypher
        assert "size(gene_terms) AS n_terms" in cypher
        assert "gene_levels AS levels_hit" in cypher
        assert "ORDER BY g.locus_tag" in cypher

    def test_mode1_per_gene(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_gene,
        )
        _, params = build_genes_by_ontology_per_gene(
            ontology="go_bp",
            organism="MED4",
            level=None,
            term_ids=["go:0006260"],
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert params["term_ids"] == ["go:0006260"]

    def test_pfam_mode1(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_gene,
        )
        cypher, _ = build_genes_by_ontology_per_gene(
            ontology="pfam",
            organism="Prochlorococcus MED4",
            level=None,
            term_ids=["pfam:PF00005", "pfam.clan:CL0023"],
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        # Pfam Mode-1 dual-label coalesce path
        assert "(tp:Pfam {id: input_tid})" in cypher
        assert "(tc:PfamClan {id: input_tid})" in cypher
        assert "coalesce(tp, tc) AS t" in cypher
        assert "Pfam_in_pfam_clan*0..1" in cypher

    def test_flat_ontology_mode2(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_gene,
        )
        cypher, _ = build_genes_by_ontology_per_gene(
            ontology="cog_category",
            organism="Prochlorococcus MED4",
            level=0,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        # Flat: t = leaf, no walk
        assert "(g:Gene {organism_name: $org})-[:Gene_in_cog_category]->(t:CogFunctionalCategory)" in cypher
        assert "(leaf)-[:" not in cypher


class TestBuildGeneOntologyTerms:
    def test_single_ontology_returns_expected_columns(self):
        """go_bp returns locus_tag, term_id, term_name in RETURN."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "locus_tag" in cypher
        assert "term_id" in cypher
        assert "term_name" in cypher

    def test_leaf_filter_hierarchical(self):
        """go_bp has hierarchy_rels, so NOT EXISTS clause is present."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "NOT EXISTS" in cypher
        assert "Biological_process_is_a_biological_process" in cypher
        assert "Biological_process_part_of_biological_process" in cypher

    def test_leaf_filter_flat_ontology(self):
        """cog_category is flat (no hierarchy_rels), so NO NOT EXISTS clause."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="cog_category", organism_name="Test Org",
        )
        assert "NOT EXISTS" not in cypher
        assert "CogFunctionalCategory" in cypher

    def test_leaf_filter_pfam(self):
        """pfam has cross-label hierarchy (parent_label), so NO NOT EXISTS."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="pfam", organism_name="Test Org",
        )
        assert "NOT EXISTS" not in cypher
        assert "Pfam" in cypher

    def test_leaf_filter_kegg(self):
        """kegg now emits NOT EXISTS like other hierarchical ontologies.

        With gene_connects_to_level removed, the leaf filter is emitted
        for KEGG too; it is a graph-structure no-op (genes only connect
        at ko leaves) but kept for consistency with other ontologies.
        """
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="kegg", organism_name="Test Org",
        )
        assert "NOT EXISTS" in cypher
        assert "KeggTerm" in cypher

    def test_verbose_false(self):
        """Compact mode does not include organism_name AS organism_name in RETURN."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org", verbose=False,
        )
        assert "AS organism_name" not in cypher

    def test_verbose_true(self):
        """Verbose mode includes organism_name AS organism_name in RETURN."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org", verbose=True,
        )
        assert "AS organism_name" in cypher

    def test_limit_clause(self):
        """LIMIT is added when limit is provided."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org", limit=10,
        )
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        """No LIMIT when limit is None."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org", limit=None,
        )
        assert "LIMIT" not in cypher

    def test_order_by(self):
        """Results are ordered by locus_tag then term id."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "ORDER BY g.locus_tag, t.id" in cypher

    def test_invalid_ontology_raises(self):
        """Invalid ontology raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_gene_ontology_terms(locus_tags=["x"], ontology="bad", organism_name="Test Org")

    def test_params_include_locus_tags(self):
        """params dict has locus_tags key."""
        _, params = build_gene_ontology_terms(
            locus_tags=["PMM0001", "PMM0002"], ontology="go_bp", organism_name="Test Org",
        )
        assert params["locus_tags"] == ["PMM0001", "PMM0002"]

    def test_offset_emits_skip(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org", limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org", limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params


class TestBuildGeneOntologyTermsSummary:
    def test_returns_cypher_and_params(self):
        """Basic call returns cypher and params."""
        cypher, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "gene_count" in cypher
        assert "term_count" in cypher
        assert "by_term" in cypher
        assert "gene_term_counts" in cypher

    def test_params_include_locus_tags(self):
        """params dict has locus_tags key."""
        _, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001", "PMM0002"], ontology="go_bp", organism_name="Test Org",
        )
        assert params["locus_tags"] == ["PMM0001", "PMM0002"]

    def test_invalid_ontology_raises(self):
        """Invalid ontology raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_gene_ontology_terms_summary(locus_tags=["x"], ontology="bad", organism_name="Test Org")


class TestGeneOntologyTermsLeafFilter:
    def test_bridge_ontology_skips_leaf_filter(self):
        from multiomics_explorer.kg.queries_lib import _gene_ontology_terms_leaf_filter, ONTOLOGY_CONFIG
        result = _gene_ontology_terms_leaf_filter(ONTOLOGY_CONFIG["brite"])
        assert result == "", "Bridge ontologies must skip leaf filter"

    def test_parent_label_ontology_still_skips(self):
        from multiomics_explorer.kg.queries_lib import _gene_ontology_terms_leaf_filter, ONTOLOGY_CONFIG
        result = _gene_ontology_terms_leaf_filter(ONTOLOGY_CONFIG["pfam"])
        assert result == ""

    def test_hierarchical_ontology_emits_filter(self):
        from multiomics_explorer.kg.queries_lib import _gene_ontology_terms_leaf_filter, ONTOLOGY_CONFIG
        result = _gene_ontology_terms_leaf_filter(ONTOLOGY_CONFIG["go_bp"])
        assert "NOT EXISTS" in result


class TestBuildGeneOntologyTermsBrite:
    def test_summary_uses_2hop_match(self):
        cypher, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="brite", organism_name="Test Org",
        )
        assert params["locus_tags"] == ["PMM0001"]
        assert params["org"] == "Test Org"
        # Must have 2-hop: Gene → KeggTerm → BriteCategory
        assert ":Gene_has_kegg_ko" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert ":BriteCategory" in cypher
        # Must NOT have direct Gene→BriteCategory (which would be wrong)
        assert "Gene_has_kegg_ko]->(t:BriteCategory)" not in cypher

    def test_detail_uses_2hop_match(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite", organism_name="Test Org",
        )
        assert ":Gene_has_kegg_ko" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert ":BriteCategory" in cypher

    def test_detail_returns_expected_columns(self):
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite", organism_name="Test Org",
        )
        for col in ["locus_tag", "term_id", "term_name"]:
            assert col in cypher


class TestBuildGeneOntologyTermsLevelTree:
    """Tests for organism, mode, level, tree parameters."""

    def test_leaf_mode_returns_level_column(self):
        """Leaf mode returns t.level AS level in RETURN."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "t.level AS level" in cypher

    def test_leaf_mode_with_level_filter(self):
        """Leaf mode with level adds t.level = $level."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
            level=2,
        )
        assert "t.level = $level" in cypher
        assert params["level"] == 2

    def test_leaf_mode_returns_tree_columns_brite(self):
        """Leaf mode for BRITE returns tree/tree_code columns."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite", organism_name="Test Org",
        )
        assert "t.tree AS tree" in cypher
        assert "t.tree_code AS tree_code" in cypher

    def test_tree_filter_adds_clause(self):
        """tree filter adds t.tree = $tree."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite", organism_name="Test Org",
            tree="Enzymes",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "Enzymes"

    def test_tree_with_non_brite_raises(self):
        """tree filter with non-brite ontology raises ValueError."""
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_gene_ontology_terms(
                locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
                tree="Enzymes",
            )

    def test_organism_scoped_match(self):
        """MATCH uses organism_name: $org and locus_tag IN $locus_tags."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "organism_name: $org" in cypher
        assert "locus_tag IN $locus_tags" in cypher
        assert params["org"] == "Test Org"

    def test_rollup_mode_uses_hierarchy_walk(self):
        """Rollup mode uses *0.., t.level = $level, DISTINCT, no NOT EXISTS."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
            mode="rollup", level=1,
        )
        assert "*0.." in cypher
        assert "t.level = $level" in cypher
        assert "DISTINCT" in cypher
        assert "NOT EXISTS" not in cypher
        assert params["level"] == 1

    def test_rollup_without_level_raises(self):
        """Rollup mode without level raises ValueError."""
        with pytest.raises(ValueError, match="level is required"):
            build_gene_ontology_terms(
                locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
                mode="rollup",
            )

    def test_rollup_brite_bridge(self):
        """Rollup with BRITE uses 2-hop bridge pattern."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite", organism_name="Test Org",
            mode="rollup", level=0,
        )
        assert ":Gene_has_kegg_ko" in cypher
        assert "KeggTerm" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert ":Brite_category_is_a_brite_category*0.." in cypher
        assert "t.level = $level" in cypher
        assert params["level"] == 0


class TestBuildGeneOntologyTermsSummaryLevelTree:
    """Tests for organism, mode, level, tree in summary builder."""

    def test_leaf_mode_collects_level_tree(self):
        """Leaf mode collects level/tree/tree_code in term objects."""
        cypher, _ = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "t.level" in cypher
        assert "t.tree" in cypher

    def test_rollup_mode_walks_hierarchy(self):
        """Rollup mode uses hierarchy walk with *0.. and level filter."""
        cypher, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
            mode="rollup", level=1,
        )
        assert "*0.." in cypher
        assert "t.level = $level" in cypher
        assert params["level"] == 1

    def test_rollup_without_level_raises(self):
        """Rollup mode without level raises ValueError."""
        with pytest.raises(ValueError, match="level is required"):
            build_gene_ontology_terms_summary(
                locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
                mode="rollup",
            )


class TestBuildSearchOntologyTcdbCazy:
    """search_ontology emits the right fulltext-index name + label for tcdb/cazy."""

    def test_search_tcdb_uses_fulltext_index(self):
        cypher, _ = build_search_ontology(ontology="tcdb", search_text="sucrose")
        assert "'tcdbFamilyFullText'" in cypher

    def test_search_cazy_uses_fulltext_index(self):
        cypher, _ = build_search_ontology(ontology="cazy", search_text="GH13")
        assert "'cazyFamilyFullText'" in cypher

    def test_tcdb_summary_uses_fulltext_index_and_label(self):
        cypher, _ = build_search_ontology_summary(
            ontology="tcdb", search_text="sucrose",
        )
        assert "'tcdbFamilyFullText'" in cypher
        assert "TcdbFamily" in cypher

    def test_cazy_summary_uses_fulltext_index_and_label(self):
        cypher, _ = build_search_ontology_summary(
            ontology="cazy", search_text="GH13",
        )
        assert "'cazyFamilyFullText'" in cypher
        assert "CazyFamily" in cypher

    def test_tcdb_no_union(self):
        """tcdb is a single-label ontology — no UNION ALL like pfam."""
        cypher, _ = build_search_ontology(ontology="tcdb", search_text="x")
        assert "UNION ALL" not in cypher

    def test_cazy_no_union(self):
        cypher, _ = build_search_ontology(ontology="cazy", search_text="x")
        assert "UNION ALL" not in cypher

    def test_tcdb_tree_filter_raises(self):
        """tree filter is BRITE-only; raises for tcdb."""
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_search_ontology(
                ontology="tcdb", search_text="x", tree="transporters",
            )

    def test_cazy_tree_filter_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_search_ontology(
                ontology="cazy", search_text="x", tree="transporters",
            )

    def test_tcdb_summary_tree_filter_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_search_ontology_summary(
                ontology="tcdb", search_text="x", tree="transporters",
            )

    def test_cazy_summary_tree_filter_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_search_ontology_summary(
                ontology="cazy", search_text="x", tree="transporters",
            )


class TestBuildGenesByOntologyTcdbCazy:
    """genes_by_ontology builders emit the right label/edge for tcdb/cazy."""

    def test_validate_tcdb_label(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_validate,
        )
        _, params = build_genes_by_ontology_validate(
            term_ids=["tcdb:1.A.1"], ontology="tcdb", level=None,
        )
        assert params["expected_labels"] == ["TcdbFamily"]

    def test_validate_cazy_label(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_validate,
        )
        _, params = build_genes_by_ontology_validate(
            term_ids=["cazy:GH13"], ontology="cazy", level=None,
        )
        assert params["expected_labels"] == ["CazyFamily"]

    def test_detail_tcdb_mode1_walks_down(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="tcdb",
            organism="Prochlorococcus MED4",
            term_ids=["tcdb:1.A.1"],
            level=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        # Mode 1: walk DOWN from input term
        assert "(t:TcdbFamily {id: input_tid})" in cypher
        assert "(leaf:TcdbFamily)" in cypher
        # Walks via tcdb hierarchy edge
        assert "Tcdb_family_is_a_tcdb_family" in cypher

    def test_detail_cazy_mode2_walks_up(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="cazy",
            organism="Prochlorococcus MED4",
            level=0,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        # Mode 2: gene → leaf, walk leaf → ancestor
        assert (
            "(g:Gene {organism_name: $org})-[:Gene_has_cazy_family]->(leaf:CazyFamily)"
            in cypher
        )
        assert "(leaf)-[:" in cypher
        assert "]->(t:CazyFamily)" in cypher
        assert "WHERE t.level = $level" in cypher

    def test_detail_tcdb_tree_filter_raises(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_genes_by_ontology_detail(
                ontology="tcdb", organism="Test Org",
                level=1, min_gene_set_size=5, max_gene_set_size=500,
                tree="transporters",
            )

    def test_detail_cazy_tree_filter_raises(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_genes_by_ontology_detail(
                ontology="cazy", organism="Test Org",
                level=0, min_gene_set_size=5, max_gene_set_size=500,
                tree="transporters",
            )

    def test_per_term_tcdb(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, _ = build_genes_by_ontology_per_term(
            ontology="tcdb",
            organism="Prochlorococcus MED4",
            level=2,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert "TcdbFamily" in cypher
        assert ":Gene_has_tcdb_family" in cypher
        assert "Tcdb_family_is_a_tcdb_family" in cypher

    def test_per_term_cazy(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, _ = build_genes_by_ontology_per_term(
            ontology="cazy",
            organism="Prochlorococcus MED4",
            level=0,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert "CazyFamily" in cypher
        assert ":Gene_has_cazy_family" in cypher
        assert "Cazy_family_is_a_cazy_family" in cypher

    def test_per_gene_tcdb(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_gene,
        )
        cypher, _ = build_genes_by_ontology_per_gene(
            ontology="tcdb",
            organism="Prochlorococcus MED4",
            level=1,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert (
            "(g:Gene {organism_name: $org})-[:Gene_has_tcdb_family]->(leaf:TcdbFamily)"
            in cypher
        )

    def test_per_gene_cazy(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_gene,
        )
        cypher, _ = build_genes_by_ontology_per_gene(
            ontology="cazy",
            organism="Prochlorococcus MED4",
            level=0,
            term_ids=None,
            min_gene_set_size=5,
            max_gene_set_size=500,
        )
        assert (
            "(g:Gene {organism_name: $org})-[:Gene_has_cazy_family]->(leaf:CazyFamily)"
            in cypher
        )


class TestBuildGeneOntologyTermsTcdbCazy:
    """gene_ontology_terms (reverse lookup) for tcdb/cazy."""

    def test_tcdb_leaf_mode_uses_label_and_edge(self):
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="tcdb", organism_name="Test Org",
        )
        assert ":Gene_has_tcdb_family" in cypher
        assert "TcdbFamily" in cypher

    def test_cazy_leaf_mode_uses_label_and_edge(self):
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="cazy", organism_name="Test Org",
        )
        assert ":Gene_has_cazy_family" in cypher
        assert "CazyFamily" in cypher

    def test_tcdb_leaf_filter_emits_not_exists(self):
        """tcdb is a single-label hierarchical ontology → leaf filter active."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="tcdb", organism_name="Test Org",
        )
        assert "NOT EXISTS" in cypher
        assert "Tcdb_family_is_a_tcdb_family" in cypher

    def test_cazy_leaf_filter_emits_not_exists(self):
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="cazy", organism_name="Test Org",
        )
        assert "NOT EXISTS" in cypher
        assert "Cazy_family_is_a_cazy_family" in cypher

    def test_tcdb_rollup_mode(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="tcdb", organism_name="Test Org",
            mode="rollup", level=0,
        )
        assert "Tcdb_family_is_a_tcdb_family*0.." in cypher
        assert "t.level = $level" in cypher
        assert params["level"] == 0

    def test_cazy_rollup_mode(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="cazy", organism_name="Test Org",
            mode="rollup", level=0,
        )
        assert "Cazy_family_is_a_cazy_family*0.." in cypher
        assert "t.level = $level" in cypher
        assert params["level"] == 0

    def test_tcdb_tree_filter_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_gene_ontology_terms(
                locus_tags=["PMM0001"], ontology="tcdb", organism_name="Test Org",
                tree="transporters",
            )

    def test_cazy_tree_filter_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_gene_ontology_terms(
                locus_tags=["PMM0001"], ontology="cazy", organism_name="Test Org",
                tree="Enzymes",
            )

    def test_tcdb_summary_uses_label_and_edge(self):
        cypher, _ = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="tcdb", organism_name="Test Org",
        )
        assert ":Gene_has_tcdb_family" in cypher
        assert "TcdbFamily" in cypher

    def test_cazy_summary_uses_label_and_edge(self):
        cypher, _ = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="cazy", organism_name="Test Org",
        )
        assert ":Gene_has_cazy_family" in cypher
        assert "CazyFamily" in cypher


class TestBuildGeneExistenceCheck:
    def test_returns_cypher(self):
        """Cypher uses OPTIONAL MATCH pattern."""
        cypher, _ = build_gene_existence_check(locus_tags=["PMM0001"])
        assert "OPTIONAL MATCH" in cypher
        assert "lt" in cypher
        assert "found" in cypher

    def test_params_include_locus_tags(self):
        """params dict includes locus_tags."""
        _, params = build_gene_existence_check(locus_tags=["PMM0001", "PMM0002"])
        assert params == {"locus_tags": ["PMM0001", "PMM0002"]}


# ---------------------------------------------------------------------------
# list_publications
# ---------------------------------------------------------------------------
class TestBuildListPublications:
    def test_no_filters(self):
        """No filters produces MATCH with no WHERE, no fulltext CALL."""
        cypher, params = build_list_publications()
        assert "MATCH (p:Publication)" in cypher
        assert "WHERE" not in cypher
        assert "fulltext" not in cypher
        assert params == {}

    def test_organism_filter(self):
        """Organism filter uses ANY on p.organisms with toLower CONTAINS."""
        cypher, params = build_list_publications(organism="MED4")
        assert "ANY(o IN p.organisms WHERE toLower(o) CONTAINS toLower($organism))" in cypher
        assert params["organism"] == "MED4"

    def test_treatment_type_filter(self):
        """Treatment type filter uses ANY on p.treatment_types with toLower match."""
        cypher, params = build_list_publications(treatment_type="coculture")
        assert "ANY(t IN p.treatment_types WHERE toLower(t) = toLower($treatment_type))" in cypher
        assert params["treatment_type"] == "coculture"

    def test_search_text(self):
        """search_text uses fulltext CALL and orders by score DESC."""
        cypher, params = build_list_publications(search_text="nitrogen")
        assert "publicationFullText" in cypher
        assert "YIELD node AS p, score" in cypher
        assert "score DESC" in cypher
        assert "score" in cypher  # in RETURN
        assert params["search_text"] == "nitrogen"

    def test_search_text_none(self):
        """No fulltext CALL when search_text is None."""
        cypher, _ = build_list_publications(search_text=None)
        assert "fulltext" not in cypher
        assert "score" not in cypher

    def test_author_filter(self):
        """Author filter uses ANY on p.authors with toLower CONTAINS."""
        cypher, params = build_list_publications(author="Sher")
        assert "ANY(a IN p.authors WHERE toLower(a) CONTAINS toLower($author))" in cypher
        assert params["author"] == "Sher"

    def test_combined_filters(self):
        """All filters produce AND-joined WHERE."""
        cypher, params = build_list_publications(
            organism="MED4", treatment_type="coculture", author="Sher",
        )
        assert "WHERE" in cypher
        assert " AND " in cypher
        assert params["organism"] == "MED4"
        assert params["treatment_type"] == "coculture"
        assert params["author"] == "Sher"

    def test_returns_expected_columns(self):
        """RETURN clause has all expected compact columns."""
        cypher, _ = build_list_publications()
        for col in [
            "doi", "title", "authors", "year", "journal",
            "study_type", "organisms", "experiment_count",
            "treatment_types", "omics_types",
        ]:
            assert col in cypher

    def test_order_by(self):
        """Without search_text, orders by year DESC then title."""
        cypher, _ = build_list_publications()
        assert "ORDER BY p.publication_year DESC, p.title" in cypher

    def test_verbose_false(self):
        """Compact mode does not include abstract or description."""
        cypher, _ = build_list_publications(verbose=False)
        assert "abstract" not in cypher
        assert "description" not in cypher

    def test_verbose_true(self):
        """Verbose mode includes abstract and description in RETURN."""
        cypher, _ = build_list_publications(verbose=True)
        assert "p.abstract AS abstract" in cypher
        assert "p.description AS description" in cypher

    def test_limit_clause(self):
        """LIMIT is added when limit is provided."""
        cypher, params = build_list_publications(limit=10)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        """No LIMIT when limit is None."""
        cypher, _ = build_list_publications(limit=None)
        assert "LIMIT" not in cypher

    def test_compact_returns_dm_rollup_fields(self):
        """Compact mode includes derived_metric_count, derived_metric_value_kinds,
        and compartments columns."""
        cypher, _ = build_list_publications()
        assert "coalesce(p.derived_metric_count, 0) AS derived_metric_count" in cypher
        assert "coalesce(p.derived_metric_value_kinds, []) AS derived_metric_value_kinds" in cypher
        assert "coalesce(p.compartments, []) AS compartments" in cypher

    def test_verbose_adds_dm_extras(self):
        """Verbose mode adds derived_metric_gene_count and derived_metric_types."""
        cypher, _ = build_list_publications(verbose=True)
        assert "coalesce(p.derived_metric_gene_count, 0) AS derived_metric_gene_count" in cypher
        assert "coalesce(p.derived_metric_types, []) AS derived_metric_types" in cypher

    def test_compartment_filter_in_where(self):
        """compartment param adds '$compartment IN coalesce(p.compartments, [])' to WHERE."""
        cypher, params = build_list_publications(compartment="vesicle")
        assert "$compartment IN coalesce(p.compartments, [])" in cypher
        assert params["compartment"] == "vesicle"

    def test_compact_dm_fields_in_search_branch(self):
        """DM rollup fields also present in the search_text (fulltext) branch."""
        cypher, _ = build_list_publications(search_text="nitrogen")
        assert "coalesce(p.derived_metric_count, 0) AS derived_metric_count" in cypher
        assert "coalesce(p.compartments, []) AS compartments" in cypher


class TestBuildListPublicationsSummary:
    def test_no_filters(self):
        """Returns total_entries and total_matching."""
        cypher, params = build_list_publications_summary()
        assert "total_entries" in cypher
        assert "total_matching" in cypher
        assert params == {}

    def test_with_filters(self):
        """Filters are applied to the matching count."""
        cypher, params = build_list_publications_summary(organism="MED4")
        assert "toLower($organism)" in cypher
        assert params["organism"] == "MED4"

    def test_search_text_uses_fulltext(self):
        """search_text uses fulltext CALL in summary query."""
        cypher, params = build_list_publications_summary(search_text="nitrogen")
        assert "publicationFullText" in cypher
        assert params["search_text"] == "nitrogen"

    def test_shares_where_clause(self):
        """Same filter logic as data builder — author filter works."""
        cypher, params = build_list_publications_summary(author="Chisholm")
        assert "ANY(a IN p.authors WHERE toLower(a) CONTAINS toLower($author))" in cypher
        assert params["author"] == "Chisholm"

    def test_uses_optional_match_for_filtered_count(self):
        """The filtered count uses OPTIONAL MATCH so an empty intersection
        still emits one row with total_matching=0 (otherwise the caller
        IndexErrors on summary[0])."""
        cypher, _ = build_list_publications_summary(organism="MED4")
        assert "OPTIONAL MATCH (p:Publication)" in cypher

    def test_summary_returns_dm_rollup_envelope_keys(self):
        """Summary RETURN includes by_value_kind, by_metric_type, by_compartment."""
        cypher, _ = build_list_publications_summary()
        assert "by_value_kind" in cypher
        assert "by_metric_type" in cypher
        assert "by_compartment" in cypher

    def test_summary_returns_by_cluster_type(self):
        """Summary RETURN includes by_cluster_type (migrated from in-memory)."""
        cypher, _ = build_list_publications_summary()
        assert "by_cluster_type" in cypher

    def test_summary_compartment_filter(self):
        """compartment param wired through to summary WHERE clause."""
        cypher, params = build_list_publications_summary(compartment="vesicle")
        assert "$compartment IN coalesce(p.compartments, [])" in cypher
        assert params["compartment"] == "vesicle"

    def test_summary_uses_apoc_frequencies(self):
        """apoc.coll.frequencies used for DM envelope keys."""
        cypher, _ = build_list_publications_summary()
        assert "apoc.coll.frequencies" in cypher
        assert "apoc.coll.flatten" in cypher


class TestBuildListPublicationsPublicationDoisFilter:
    """Coverage for the publication_dois filter shared across detail + summary
    builders. Mirrors the experiment_ids pattern on list_experiments."""

    def test_filter_in_cypher(self):
        cypher, params = build_list_publications(
            publication_dois=["10.1038/ismej.2016.70", "10.1101/foo"],
        )
        assert "toLower(p.doi) IN $publication_dois" in cypher
        assert params["publication_dois"] == [
            "10.1038/ismej.2016.70", "10.1101/foo",
        ]

    def test_case_insensitive(self):
        """Input DOIs are lowercased to match the toLower() comparison."""
        _, params = build_list_publications(
            publication_dois=["10.1038/ISMEJ.2016.70"],
        )
        assert params["publication_dois"] == ["10.1038/ismej.2016.70"]

    def test_combines_with_organism(self):
        cypher, params = build_list_publications(
            organism="MED4", publication_dois=["10.1038/ismej.2016.70"],
        )
        assert "toLower(p.doi) IN $publication_dois" in cypher
        assert "$organism" in cypher
        assert params["publication_dois"] == ["10.1038/ismej.2016.70"]

    def test_none_omits_clause(self):
        cypher, params = build_list_publications()
        assert "publication_dois" not in params
        assert "$publication_dois" not in cypher

    def test_empty_list_omits_clause(self):
        # `if publication_dois:` is false for empty lists — no clause.
        cypher, params = build_list_publications(publication_dois=[])
        assert "publication_dois" not in params
        assert "$publication_dois" not in cypher

    def test_summary_filter_in_cypher(self):
        cypher, params = build_list_publications_summary(
            publication_dois=["10.1038/ismej.2016.70"],
        )
        assert "toLower(p.doi) IN $publication_dois" in cypher
        assert params["publication_dois"] == ["10.1038/ismej.2016.70"]


class TestBuildListExperiments:
    def test_no_filters(self):
        """No filters produces MATCH with no WHERE, no fulltext CALL."""
        cypher, params = build_list_experiments()
        assert "MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)" in cypher
        assert "WHERE" not in cypher
        assert "fulltext" not in cypher
        assert params == {}

    def test_returns_authors_column(self):
        """RETURN columns include authors sourced from Publication.authors (null-safe)."""
        cypher, _ = build_list_experiments()
        assert "coalesce(p.authors, []) AS authors" in cypher

    def test_organism_filter(self):
        """Organism filter matches profiled organism only (no OR against coculture_partner)."""
        cypher, params = build_list_experiments(organism="MED4")
        assert "ALL(word IN split(toLower($organism)" in cypher
        assert "toLower(e.organism_name) CONTAINS word" in cypher
        # No OR against coculture_partner — that footgun is gone.
        assert "toLower(e.coculture_partner) CONTAINS word" not in cypher
        assert params["organism"] == "MED4"

    def test_organism_and_coculture_partner_compose_with_and(self):
        """organism= and coculture_partner= compose with AND, not OR."""
        cypher, params = build_list_experiments(
            organism="MED4", coculture_partner="Alteromonas",
        )
        assert "toLower(e.organism_name) CONTAINS word" in cypher
        assert "toLower(e.coculture_partner) CONTAINS toLower($partner)" in cypher
        # Two clauses joined by AND, not OR.
        assert " AND " in cypher
        # No OR anywhere — the organism predicate must not be re-OR'd, and the
        # partner predicate composes via outer AND. See spec F2.
        assert " OR " not in cypher
        assert params["organism"] == "MED4"
        assert params["partner"] == "Alteromonas"

    def test_treatment_type_filter(self):
        """Treatment type filter uses ANY() for array property."""
        cypher, params = build_list_experiments(treatment_type=["coculture", "nitrogen_stress"])
        assert "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)" in cypher
        assert params["treatment_types"] == ["coculture", "nitrogen_stress"]

    def test_treatment_type_case_insensitive(self):
        """Treatment type list values are lowercased."""
        _, params = build_list_experiments(treatment_type=["COCULTURE"])
        assert params["treatment_types"] == ["coculture"]

    def test_omics_type_filter(self):
        """Omics type filter uses toUpper IN with list param."""
        cypher, params = build_list_experiments(omics_type=["rnaseq", "proteomics"])
        assert "toUpper(e.omics_type) IN $omics_types" in cypher
        assert params["omics_types"] == ["RNASEQ", "PROTEOMICS"]

    def test_publication_doi_filter(self):
        """Publication DOI filter uses toLower IN with list param."""
        cypher, params = build_list_experiments(publication_doi=["10.1038/ismej.2016.70"])
        assert "toLower(p.doi) IN $dois" in cypher
        assert params["dois"] == ["10.1038/ismej.2016.70"]

    def test_coculture_partner_filter(self):
        """Coculture partner filter uses toLower CONTAINS."""
        cypher, params = build_list_experiments(coculture_partner="Alteromonas")
        assert "toLower(e.coculture_partner) CONTAINS toLower($partner)" in cypher
        assert params["partner"] == "Alteromonas"

    def test_search_text_fulltext(self):
        """search_text uses experimentFullText index and orders by score DESC."""
        cypher, params = build_list_experiments(search_text="continuous light")
        assert "experimentFullText" in cypher
        assert "YIELD node AS e, score" in cypher
        assert "score DESC" in cypher
        assert "score" in cypher
        assert params["search_text"] == "continuous light"

    def test_search_text_none(self):
        """No fulltext CALL when search_text is None."""
        cypher, _ = build_list_experiments(search_text=None)
        assert "fulltext" not in cypher
        assert "score" not in cypher

    def test_time_course_only(self):
        """time_course_only adds WHERE is_time_course = 'true'."""
        cypher, _ = build_list_experiments(time_course_only=True)
        assert "e.is_time_course = 'true'" in cypher

    def test_combined_filters(self):
        """Multiple filters produce AND-joined WHERE."""
        cypher, params = build_list_experiments(
            organism="MED4", treatment_type=["coculture"], omics_type=["RNASEQ"],
        )
        assert "WHERE" in cypher
        assert " AND " in cypher
        assert params["organism"] == "MED4"
        assert params["treatment_types"] == ["coculture"]
        assert params["omics_types"] == ["RNASEQ"]

    def test_returns_expected_columns(self):
        """RETURN clause has all expected compact columns."""
        cypher, _ = build_list_experiments()
        for col in [
            "experiment_id", "experiment_name", "publication_doi",
            "organism_name", "treatment_type", "coculture_partner",
            "omics_type", "is_time_course",
            "table_scope", "table_scope_detail",
            "gene_count", "significant_up_count",
            "significant_down_count",
            "time_point_count", "time_point_labels", "time_point_orders",
            "time_point_hours", "time_point_totals",
            "time_point_significant_up", "time_point_significant_down",
        ]:
            assert col in cypher

    def test_verbose_false(self):
        """Compact mode does not include verbose columns."""
        cypher, _ = build_list_experiments(verbose=False)
        assert "publication_title" not in cypher
        assert "e.treatment AS treatment" not in cypher
        assert "light_condition" not in cypher

    def test_verbose_true(self):
        """Verbose mode includes publication_title, treatment, etc."""
        cypher, _ = build_list_experiments(verbose=True)
        assert "p.title AS publication_title" in cypher
        assert "e.treatment AS treatment" in cypher
        assert "e.control AS control" in cypher
        assert "e.light_condition AS light_condition" in cypher
        assert "e.medium AS medium" in cypher
        assert "e.temperature AS temperature" in cypher
        assert "e.statistical_test AS statistical_test" in cypher
        assert "e.experimental_context AS experimental_context" in cypher

    def test_order_by(self):
        """Without search_text, orders by year DESC, organism, name."""
        cypher, _ = build_list_experiments()
        assert "ORDER BY p.publication_year DESC, e.organism_name, e.name" in cypher

    def test_limit_clause(self):
        """LIMIT is added when limit is provided."""
        cypher, params = build_list_experiments(limit=10)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        """No LIMIT when limit is None."""
        cypher, _ = build_list_experiments(limit=None)
        assert "LIMIT" not in cypher

    def test_offset_emits_skip(self):
        cypher, params = build_list_experiments(
            limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_list_experiments(
            limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_table_scope_filter(self):
        """table_scope filter uses IN with list param."""
        cypher, params = build_list_experiments(table_scope=["all_detected_genes"])
        assert "e.table_scope IN $table_scopes" in cypher
        assert params["table_scopes"] == ["all_detected_genes"]

    def test_table_scope_multiple_values(self):
        """table_scope with multiple values produces a list param."""
        cypher, params = build_list_experiments(
            table_scope=["all_detected_genes", "significant_only"],
        )
        assert "e.table_scope IN $table_scopes" in cypher
        assert params["table_scopes"] == ["all_detected_genes", "significant_only"]

    def test_table_scope_none_no_filter(self):
        """table_scope=None does not add filter."""
        cypher, _ = build_list_experiments(table_scope=None)
        assert "table_scopes" not in cypher

    def test_table_scope_combined_with_organism(self):
        """table_scope + organism produces AND-joined WHERE."""
        cypher, params = build_list_experiments(
            organism="MED4", table_scope=["all_detected_genes"],
        )
        assert "e.table_scope IN $table_scopes" in cypher
        assert "toLower($organism)" in cypher
        assert " AND " in cypher

    def test_growth_phases_filter(self):
        """growth_phases filter adds ANY-match condition with lowercased params."""
        cypher, params = build_list_experiments(growth_phases=["exponential", "nutrient_limited"])
        assert "growth_phases" in cypher
        assert "toLower(gp) IN $growth_phases" in cypher
        assert params["growth_phases"] == ["exponential", "nutrient_limited"]

    def test_growth_phases_case_insensitive(self):
        """growth_phases values are lowercased for case-insensitive matching."""
        _, params = build_list_experiments(growth_phases=["Exponential"])
        assert params["growth_phases"] == ["exponential"]

    def test_growth_phases_none_no_filter(self):
        """growth_phases=None does not add filter."""
        cypher, _ = build_list_experiments(growth_phases=None)
        assert "$growth_phases" not in cypher

    def test_returns_growth_phases(self):
        """Returns growth_phases and time_point_growth_phases columns."""
        cypher, _ = build_list_experiments()
        assert "growth_phases" in cypher
        assert "time_point_growth_phases" in cypher


class TestBuildGeneStub:
    def test_returns_cypher_and_params(self):
        cypher, params = build_gene_stub(gene_id="PMM0001")
        assert "MATCH (g:Gene {locus_tag: $lt})" in cypher
        assert params["lt"] == "PMM0001"

    def test_returns_expected_columns(self):
        cypher, _ = build_gene_stub(gene_id="PMM0001")
        for col in ["locus_tag", "gene_name", "product", "organism_name"]:
            assert col in cypher

    def test_no_limit_or_order(self):
        """gene_stub is a simple single-gene lookup — no LIMIT or ORDER BY."""
        cypher, _ = build_gene_stub(gene_id="PMM0001")
        assert "LIMIT" not in cypher
        assert "ORDER BY" not in cypher

    def test_param_name_is_lt(self):
        """Parameter key is 'lt' (matching the Cypher $lt variable)."""
        _, params = build_gene_stub(gene_id="SYNW0305")
        assert params == {"lt": "SYNW0305"}


class TestBuildListExperimentsExperimentIdsFilter:
    """Coverage for the experiment_ids filter shared across detail + summary
    builders (B2 #1)."""

    def test_filter_in_cypher(self):
        cypher, params = build_list_experiments(experiment_ids=["exp_a", "exp_b"])
        assert "e.id IN $experiment_ids" in cypher
        assert params["experiment_ids"] == ["exp_a", "exp_b"]

    def test_combines_with_organism(self):
        cypher, params = build_list_experiments(
            organism="MED4", experiment_ids=["exp_a"],
        )
        assert "e.id IN $experiment_ids" in cypher
        assert "$organism" in cypher
        assert params["experiment_ids"] == ["exp_a"]

    def test_none_omits_clause(self):
        cypher, params = build_list_experiments()
        assert "experiment_ids" not in params
        assert "$experiment_ids" not in cypher

    def test_empty_list_omits_clause(self):
        # `if experiment_ids:` is false for empty lists — no clause.
        cypher, params = build_list_experiments(experiment_ids=[])
        assert "experiment_ids" not in params
        assert "$experiment_ids" not in cypher

    def test_summary_filter_in_cypher(self):
        cypher, params = build_list_experiments_summary(
            experiment_ids=["exp_a", "exp_b"],
        )
        assert "e.id IN $experiment_ids" in cypher
        assert params["experiment_ids"] == ["exp_a", "exp_b"]


class TestBuildListExperimentsDistinctGeneCount:
    """Coverage for the precomputed distinct_gene_count RETURN column (B2 #2)."""

    def test_returns_distinct_gene_count(self):
        cypher, _ = build_list_experiments()
        assert "e.distinct_gene_count AS distinct_gene_count" in cypher

    def test_distinct_gene_count_returned_with_filters(self):
        # Column should still be in RETURN when filters narrow the result.
        cypher, _ = build_list_experiments(organism="MED4", verbose=True)
        assert "distinct_gene_count" in cypher


class TestBuildListExperimentsSummary:
    def test_no_filters(self):
        """Returns aggregation columns via apoc.coll.frequencies."""
        cypher, params = build_list_experiments_summary()
        assert "total_matching" in cypher
        assert "time_course_count" in cypher
        assert "apoc.coll.frequencies" in cypher
        assert "by_organism" in cypher
        assert "by_treatment_type" in cypher
        assert "by_omics_type" in cypher
        assert "by_publication" in cypher
        assert params == {}

    def test_with_filters(self):
        """Filters are applied to the summary query."""
        cypher, params = build_list_experiments_summary(organism="MED4")
        assert "ALL(word IN split(toLower($organism)" in cypher
        assert params["organism"] == "MED4"

    def test_search_text_fulltext(self):
        """search_text uses experimentFullText index and includes score distribution."""
        cypher, params = build_list_experiments_summary(search_text="nitrogen")
        assert "experimentFullText" in cypher
        assert "score_max" in cypher
        assert "score_median" in cypher
        assert params["search_text"] == "nitrogen"

    def test_search_text_none_no_scores(self):
        """No score distribution when search_text is None."""
        cypher, _ = build_list_experiments_summary()
        assert "score_max" not in cypher
        assert "score_median" not in cypher

    def test_shares_where_clause(self):
        """Same filter logic as detail builder — treatment_type array filter."""
        cypher, params = build_list_experiments_summary(
            treatment_type=["coculture", "nitrogen_stress"]
        )
        assert "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)" in cypher
        assert params["treatment_types"] == ["coculture", "nitrogen_stress"]

    def test_returns_aggregation_keys(self):
        """RETURN has all expected aggregation keys."""
        cypher, _ = build_list_experiments_summary()
        for key in [
            "total_matching", "time_course_count",
            "by_organism", "by_treatment_type", "by_omics_type",
            "by_publication", "by_table_scope",
        ]:
            assert key in cypher

    def test_table_scope_filter(self):
        """table_scope filter applied to summary query."""
        cypher, params = build_list_experiments_summary(
            table_scope=["all_detected_genes"],
        )
        assert "e.table_scope IN $table_scopes" in cypher
        assert params["table_scopes"] == ["all_detected_genes"]

    def test_table_scope_none_no_filter(self):
        """table_scope=None does not add filter to summary."""
        cypher, _ = build_list_experiments_summary(table_scope=None)
        assert "table_scopes" not in cypher

    def test_summary_returns_by_growth_phase(self):
        """Summary includes by_growth_phase frequency breakdown."""
        cypher, _ = build_list_experiments_summary()
        assert "by_growth_phase" in cypher


class TestBuildListExperimentsDmRollup:
    """Task 4 — DM rollup per-row fields + compartment filter + summary rollups."""

    # --- Compact per-row DM fields ---
    def test_compact_includes_derived_metric_count(self):
        cypher, _ = build_list_experiments()
        assert "derived_metric_count" in cypher

    def test_compact_includes_derived_metric_value_kinds(self):
        cypher, _ = build_list_experiments()
        assert "derived_metric_value_kinds" in cypher

    def test_compact_includes_compartment_scalar(self):
        """Compact RETURN has singular 'compartment' (scalar, not list)."""
        cypher, _ = build_list_experiments()
        assert "e.compartment AS compartment" in cypher

    def test_compact_search_branch_also_has_dm_fields(self):
        """Both search and non-search branches include DM fields."""
        cypher, _ = build_list_experiments(search_text="diel")
        assert "derived_metric_count" in cypher
        assert "derived_metric_value_kinds" in cypher
        assert "e.compartment AS compartment" in cypher

    # --- Verbose-only DM fields ---
    def test_verbose_false_no_dm_extra(self):
        cypher, _ = build_list_experiments(verbose=False)
        assert "derived_metric_gene_count" not in cypher
        assert "derived_metric_types" not in cypher
        assert "reports_derived_metric_types" not in cypher

    def test_verbose_true_includes_dm_gene_count(self):
        cypher, _ = build_list_experiments(verbose=True)
        assert "derived_metric_gene_count" in cypher

    def test_verbose_true_includes_derived_metric_types(self):
        cypher, _ = build_list_experiments(verbose=True)
        assert "derived_metric_types" in cypher

    def test_verbose_true_includes_reports_derived_metric_types(self):
        cypher, _ = build_list_experiments(verbose=True)
        assert "reports_derived_metric_types" in cypher

    def test_verbose_search_branch_also_has_dm_extras(self):
        """Verbose DM fields present in search-text branch too."""
        cypher, _ = build_list_experiments(search_text="diel", verbose=True)
        assert "derived_metric_gene_count" in cypher
        assert "derived_metric_types" in cypher
        assert "reports_derived_metric_types" in cypher

    # --- compartment filter ---
    def test_compartment_filter_emits_scalar_equality(self):
        """e.compartment = $compartment (NOT IN-on-list)."""
        cypher, params = build_list_experiments(compartment="vesicle")
        assert "e.compartment = $compartment" in cypher
        assert params["compartment"] == "vesicle"

    def test_compartment_none_no_clause(self):
        cypher, params = build_list_experiments(compartment=None)
        assert "$compartment" not in cypher
        assert "compartment" not in params

    def test_compartment_combines_with_organism(self):
        cypher, params = build_list_experiments(organism="MED4", compartment="vesicle")
        assert "e.compartment = $compartment" in cypher
        assert "organism" in params
        assert " AND " in cypher

    def test_compartment_filter_summary_builder(self):
        cypher, params = build_list_experiments_summary(compartment="vesicle")
        assert "e.compartment = $compartment" in cypher
        assert params["compartment"] == "vesicle"

    # --- Summary DM rollup keys ---
    def test_summary_includes_by_value_kind(self):
        cypher, _ = build_list_experiments_summary()
        assert "by_value_kind" in cypher

    def test_summary_includes_by_metric_type(self):
        cypher, _ = build_list_experiments_summary()
        assert "by_metric_type" in cypher

    def test_summary_includes_by_compartment(self):
        cypher, _ = build_list_experiments_summary()
        assert "by_compartment" in cypher

    def test_summary_compartment_uses_collect_not_flatten(self):
        """e.compartment is scalar — collect(e.compartment), not flatten(collect(...))."""
        cypher, _ = build_list_experiments_summary()
        # collect(e.compartment) should be present
        assert "collect(e.compartment)" in cypher
        # Should not try to flatten compartment (it's a scalar)
        assert "flatten(\n       collect(coalesce(e.compartment" not in cypher
        assert "flatten(collect(e.compartment" not in cypher

    def test_summary_search_branch_includes_dm_rollups(self):
        """DM rollup keys present in search-text summary branch too."""
        cypher, _ = build_list_experiments_summary(search_text="diel")
        assert "by_value_kind" in cypher
        assert "by_metric_type" in cypher
        assert "by_compartment" in cypher


# ---------------------------------------------------------------------------
# Organism pre-validation builders
# ---------------------------------------------------------------------------


class TestBuildResolveOrganismForOrganism:
    def test_basic(self):
        cypher, params = build_resolve_organism_for_organism(organism="MED4")
        assert "e.gene_count > 0" in cypher
        assert "organisms" in cypher
        assert params["organism"] == "MED4"

    def test_fuzzy_match(self):
        cypher, _ = build_resolve_organism_for_organism(organism="MED4")
        assert "toLower($organism)" in cypher
        assert "CONTAINS" in cypher


class TestBuildResolveOrganismForLocusTags:
    def test_basic(self):
        cypher, params = build_resolve_organism_for_locus_tags(
            locus_tags=["PMM0001"]
        )
        assert "Gene {locus_tag: lt}" in cypher
        assert "organisms" in cypher
        assert params["locus_tags"] == ["PMM0001"]


class TestBuildResolveOrganismForExperiments:
    def test_basic(self):
        cypher, params = build_resolve_organism_for_experiments(
            experiment_ids=["exp1"]
        )
        assert "Experiment {id: eid}" in cypher
        assert "organisms" in cypher
        assert params["experiment_ids"] == ["exp1"]


# ---------------------------------------------------------------------------
# Differential expression summary builders
# ---------------------------------------------------------------------------


class TestBuildDifferentialExpressionByGeneSummaryGlobal:
    def test_no_filters(self):
        cypher, params = (
            build_differential_expression_by_gene_summary_global()
        )
        assert "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)" in cypher
        assert "WHERE" not in cypher
        assert params == {}

    def test_organism_filter(self):
        cypher, params = (
            build_differential_expression_by_gene_summary_global(
                organism="MED4"
            )
        )
        assert "toLower($organism)" in cypher
        assert params["organism"] == "MED4"

    def test_locus_tags_filter(self):
        cypher, params = (
            build_differential_expression_by_gene_summary_global(
                locus_tags=["PMM0001"]
            )
        )
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == ["PMM0001"]

    def test_experiment_ids_filter(self):
        cypher, params = (
            build_differential_expression_by_gene_summary_global(
                experiment_ids=["exp1"]
            )
        )
        assert "e.id IN $experiment_ids" in cypher
        assert params["experiment_ids"] == ["exp1"]

    def test_direction_up(self):
        cypher, _ = build_differential_expression_by_gene_summary_global(
            direction="up"
        )
        assert "r.expression_status = 'significant_up'" in cypher

    def test_direction_down(self):
        cypher, _ = build_differential_expression_by_gene_summary_global(
            direction="down"
        )
        assert "r.expression_status = 'significant_down'" in cypher

    def test_significant_only(self):
        cypher, _ = build_differential_expression_by_gene_summary_global(
            significant_only=True
        )
        assert "r.expression_status <> 'not_significant'" in cypher

    def test_direction_overrides_significant_only(self):
        cypher, _ = build_differential_expression_by_gene_summary_global(
            direction="up", significant_only=True
        )
        assert "r.expression_status = 'significant_up'" in cypher
        # The <> "not_significant" appears in CASE expressions (for median/max),
        # but should NOT appear in the WHERE clause when direction is set.
        where_part = cypher.split("RETURN")[0]
        assert "r.expression_status <> 'not_significant'" not in where_part

    def test_returns_expected_keys(self):
        cypher, _ = build_differential_expression_by_gene_summary_global()
        for key in [
            "total_matching", "matching_genes", "rows_by_status",
            "rows_by_treatment_type", "median_abs_log2fc", "max_abs_log2fc",
        ]:
            assert key in cypher

    def test_combined_filters(self):
        cypher, params = (
            build_differential_expression_by_gene_summary_global(
                organism="MED4",
                locus_tags=["PMM0001"],
                experiment_ids=["exp1"],
                significant_only=True,
            )
        )
        assert "WHERE" in cypher
        assert "AND" in cypher
        assert params["organism"] == "MED4"
        assert params["locus_tags"] == ["PMM0001"]
        assert params["experiment_ids"] == ["exp1"]


class TestBuildDifferentialExpressionByGeneSummaryByExperiment:
    def test_no_filters(self):
        cypher, params = (
            build_differential_expression_by_gene_summary_by_experiment()
        )
        assert "Changes_expression_of" in cypher
        assert "organism_name" in cypher
        assert "experiments" in cypher
        assert params == {}

    def test_returns_nested_timepoints(self):
        cypher, _ = (
            build_differential_expression_by_gene_summary_by_experiment()
        )
        assert "timepoint" in cypher
        assert "timepoint_hours" in cypher
        assert "timepoint_order" in cypher

    def test_returns_experiment_metadata(self):
        cypher, _ = (
            build_differential_expression_by_gene_summary_by_experiment()
        )
        for key in [
            "experiment_id", "experiment_name", "treatment_type",
            "omics_type", "is_time_course",
        ]:
            assert key in cypher

    def test_organism_filter(self):
        cypher, params = (
            build_differential_expression_by_gene_summary_by_experiment(
                organism="HOT1A3"
            )
        )
        assert "toLower($organism)" in cypher
        assert params["organism"] == "HOT1A3"


class TestBuildDifferentialExpressionByGeneSummaryDiagnostics:
    def test_no_locus_tags(self):
        """Without locus_tags, returns empty not_found/no_expression."""
        cypher, params = (
            build_differential_expression_by_gene_summary_diagnostics(
                organism="MED4"
            )
        )
        assert "[] AS not_found" in cypher
        assert "[] AS no_expression" in cypher
        assert "top_categories" in cypher
        assert "UNWIND $locus_tags" not in cypher

    def test_with_locus_tags(self):
        """With locus_tags, uses UNWIND for batch diagnostics."""
        cypher, params = (
            build_differential_expression_by_gene_summary_diagnostics(
                locus_tags=["PMM0001", "FAKE_TAG"]
            )
        )
        assert "UNWIND $locus_tags AS lt" in cypher
        assert "not_found" in cypher
        assert "no_expression" in cypher
        assert "top_categories" in cypher
        assert params["locus_tags"] == ["PMM0001", "FAKE_TAG"]

    def test_with_locus_tags_and_experiment_ids(self):
        """Experiment filter is in where_block_no_lt."""
        cypher, params = (
            build_differential_expression_by_gene_summary_diagnostics(
                locus_tags=["PMM0001"],
                experiment_ids=["exp1"],
            )
        )
        assert "e.id IN $experiment_ids" in cypher
        assert params["experiment_ids"] == ["exp1"]
        # locus_tags NOT in WHERE (applied via UNWIND)
        assert "g.locus_tag IN $locus_tags" not in cypher

    def test_top_categories_limited_to_5(self):
        cypher, _ = (
            build_differential_expression_by_gene_summary_diagnostics()
        )
        assert "[0..5]" in cypher

    def test_uses_count_r_not_count_star(self):
        """count(r) correctly handles OPTIONAL MATCH nulls."""
        cypher, _ = (
            build_differential_expression_by_gene_summary_diagnostics(
                locus_tags=["PMM0001"]
            )
        )
        assert "count(r)" in cypher
        assert "count(*)" not in cypher


# ---------------------------------------------------------------------------
# Differential expression detail builder
# ---------------------------------------------------------------------------


class TestBuildDifferentialExpressionByGene:
    def test_no_filters(self):
        cypher, params = build_differential_expression_by_gene()
        assert "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)" in cypher
        assert "WHERE" not in cypher
        assert params == {}

    def test_returns_compact_columns(self):
        cypher, _ = build_differential_expression_by_gene()
        for col in [
            "locus_tag", "gene_name", "experiment_id", "treatment_type",
            "timepoint", "timepoint_hours", "timepoint_order",
            "log2fc", "padj", "rank", "expression_status",
        ]:
            assert col in cypher

    def test_verbose_false_no_extra_columns(self):
        cypher, _ = build_differential_expression_by_gene(verbose=False)
        assert "product" not in cypher
        assert "experiment_name" not in cypher
        assert "gene_category" not in cypher

    def test_verbose_true_adds_columns(self):
        cypher, _ = build_differential_expression_by_gene(verbose=True)
        for col in [
            "product", "experiment_name", "treatment",
            "gene_category", "omics_type", "coculture_partner",
        ]:
            assert col in cypher

    def test_limit(self):
        cypher, params = build_differential_expression_by_gene(limit=10)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        cypher, params = build_differential_expression_by_gene(limit=None)
        assert "LIMIT" not in cypher
        assert "limit" not in params

    def test_order_by(self):
        cypher, _ = build_differential_expression_by_gene()
        assert "ORDER BY ABS(r.log2_fold_change) DESC" in cypher
        assert "g.locus_tag ASC" in cypher

    def test_organism_filter(self):
        cypher, params = build_differential_expression_by_gene(
            organism="MED4"
        )
        assert "toLower($organism)" in cypher
        assert params["organism"] == "MED4"

    def test_combined_filters(self):
        cypher, params = build_differential_expression_by_gene(
            organism="MED4",
            locus_tags=["PMM0001"],
            experiment_ids=["exp1"],
            direction="up",
            verbose=True,
            limit=20,
        )
        assert "WHERE" in cypher
        assert params["organism"] == "MED4"
        assert params["locus_tags"] == ["PMM0001"]
        assert params["experiment_ids"] == ["exp1"]
        assert params["limit"] == 20
        assert "r.expression_status = 'significant_up'" in cypher
        assert "product" in cypher

    def test_offset_emits_skip(self):
        cypher, params = build_differential_expression_by_gene(
            limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_differential_expression_by_gene(
            limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_returns_rank_up_rank_down(self):
        """Detail query includes directional rank columns."""
        cypher, _ = build_differential_expression_by_gene()
        assert "rank_up" in cypher
        assert "rank_down" in cypher


class TestBuildSearchHomologGroups:
    """Tests for build_search_homolog_groups."""

    def test_no_filters(self):
        cypher, params = build_search_homolog_groups(search_text="photosynthesis")
        assert "orthologGroupFullText" in cypher
        assert "$search_text" in cypher
        assert params["search_text"] == "photosynthesis"
        assert "WHERE" not in cypher

    def test_source_filter(self):
        cypher, params = build_search_homolog_groups(
            search_text="kinase", source="cyanorak")
        assert "og.source = $source" in cypher
        assert params["source"] == "cyanorak"

    def test_taxonomic_level_filter(self):
        cypher, params = build_search_homolog_groups(
            search_text="kinase", taxonomic_level="curated")
        assert "og.taxonomic_level = $level" in cypher
        assert params["level"] == "curated"

    def test_max_specificity_rank_filter(self):
        cypher, params = build_search_homolog_groups(
            search_text="kinase", max_specificity_rank=1)
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["max_rank"] == 1

    def test_combined_filters(self):
        cypher, params = build_search_homolog_groups(
            search_text="kinase", source="cyanorak", max_specificity_rank=0)
        assert "og.source = $source" in cypher
        assert "og.specificity_rank <= $max_rank" in cypher
        assert "AND" in cypher

    def test_returns_expected_columns(self):
        cypher, _ = build_search_homolog_groups(search_text="test")
        for col in ["group_id", "group_name", "consensus_gene_name",
                     "consensus_product", "source", "taxonomic_level",
                     "specificity_rank", "member_count", "organism_count"]:
            assert f"AS {col}" in cypher
        # score is returned directly from YIELD, not aliased
        assert "score" in cypher

    def test_verbose_columns(self):
        cypher, _ = build_search_homolog_groups(search_text="test", verbose=True)
        for col in ["description", "functional_description", "genera",
                     "has_cross_genus_members"]:
            assert f"AS {col}" in cypher

    def test_verbose_false_excludes_columns(self):
        cypher, _ = build_search_homolog_groups(search_text="test", verbose=False)
        assert "AS description" not in cypher
        assert "AS functional_description" not in cypher

    def test_order_by(self):
        cypher, _ = build_search_homolog_groups(search_text="test")
        assert "ORDER BY score DESC" in cypher

    def test_limit_clause(self):
        cypher, params = build_search_homolog_groups(search_text="test", limit=10)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        cypher, params = build_search_homolog_groups(search_text="test")
        assert "LIMIT" not in cypher
        assert "limit" not in params

    def test_offset_emits_skip(self):
        cypher, params = build_search_homolog_groups(
            search_text="test", limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_search_homolog_groups(
            search_text="test", limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_cyanorak_roles_filter(self):
        cypher, params = build_search_homolog_groups(
            search_text="test", cyanorak_roles=["cyanorak.role:G.3"])
        assert "Og_has_cyanorak_role" in cypher
        assert "$cyanorak_roles" in cypher
        assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]

    def test_cog_categories_filter(self):
        cypher, params = build_search_homolog_groups(
            search_text="test", cog_categories=["cog.category:J"])
        assert "Og_in_cog_category" in cypher
        assert "$cog_categories" in cypher
        assert params["cog_categories"] == ["cog.category:J"]

    def test_ontology_filter_none_no_clause(self):
        cypher, params = build_search_homolog_groups(search_text="test")
        assert "Og_has_cyanorak_role" not in cypher
        assert "Og_in_cog_category" not in cypher

    def test_verbose_includes_ontology_columns(self):
        cypher, _ = build_search_homolog_groups(search_text="test", verbose=True)
        assert "cyanorak_roles" in cypher
        assert "cog_categories" in cypher
        assert "Og_has_cyanorak_role" in cypher
        assert "Og_in_cog_category" in cypher

    def test_verbose_false_excludes_ontology_columns(self):
        cypher, _ = build_search_homolog_groups(search_text="test", verbose=False)
        assert "cyanorak_roles" not in cypher
        assert "cog_categories" not in cypher


class TestBuildSearchHomologGroupsSummary:
    """Tests for build_search_homolog_groups_summary."""

    def test_no_filters(self):
        cypher, params = build_search_homolog_groups_summary(search_text="test")
        assert "orthologGroupFullText" in cypher
        assert "total_matching" in cypher
        assert "score_max" in cypher
        assert "score_median" in cypher
        assert "by_source" in cypher
        assert "by_level" in cypher
        assert "total_entries" in cypher

    def test_with_source_filter(self):
        cypher, params = build_search_homolog_groups_summary(
            search_text="test", source="cyanorak")
        assert "og.source = $source" in cypher

    def test_shares_where_clause(self):
        """Summary and detail should produce the same WHERE for same filters."""
        _, sum_params = build_search_homolog_groups_summary(
            search_text="test", source="cyanorak", max_specificity_rank=1)
        _, det_params = build_search_homolog_groups(
            search_text="test", source="cyanorak", max_specificity_rank=1)
        # Same filter params (detail has extra verbose/limit keys)
        assert sum_params["source"] == det_params["source"]
        assert sum_params["max_rank"] == det_params["max_rank"]

    def test_cyanorak_roles_filter_forwarded(self):
        cypher, params = build_search_homolog_groups_summary(
            search_text="test", cyanorak_roles=["cyanorak.role:G.3"])
        assert "Og_has_cyanorak_role" in cypher
        assert params["cyanorak_roles"] == ["cyanorak.role:G.3"]

    def test_cog_categories_filter_forwarded(self):
        cypher, params = build_search_homolog_groups_summary(
            search_text="test", cog_categories=["cog.category:J"])
        assert "Og_in_cog_category" in cypher
        assert params["cog_categories"] == ["cog.category:J"]

    def test_summary_includes_top_ontology_breakdowns(self):
        cypher, _ = build_search_homolog_groups_summary(search_text="test")
        assert "top_cyanorak_roles" in cypher
        assert "top_cog_categories" in cypher
        assert "Og_has_cyanorak_role" in cypher
        assert "Og_in_cog_category" in cypher


class TestBuildGenesByHomologGroup:
    """Tests for build_genes_by_homolog_group."""

    def test_single_group_id(self):
        cypher, params = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_00000570"])
        assert "Gene_in_ortholog_group" in cypher
        assert "$group_ids" in cypher
        assert params["group_ids"] == ["cyanorak:CK_00000570"]

    def test_multiple_group_ids(self):
        cypher, params = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_00000570", "eggnog:COG0592@2"])
        assert len(params["group_ids"]) == 2

    def test_organisms_filter_clause(self):
        cypher, params = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"], organisms=["MED4"])
        assert "$organisms IS NULL" in cypher
        assert params["organisms"] == ["MED4"]

    def test_no_organisms_filter(self):
        cypher, params = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"])
        assert params["organisms"] is None

    def test_returns_expected_columns(self):
        cypher, _ = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"])
        for col in ["locus_tag", "gene_name", "product",
                     "organism_name", "gene_category", "group_id"]:
            assert f"AS {col}" in cypher

    def test_verbose_columns(self):
        cypher, _ = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"], verbose=True)
        for col in ["gene_summary", "function_description",
                     "consensus_product", "source"]:
            assert f"AS {col}" in cypher

    def test_verbose_false_excludes_columns(self):
        cypher, _ = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"], verbose=False)
        assert "AS gene_summary" not in cypher
        assert "AS function_description" not in cypher

    def test_order_by(self):
        cypher, _ = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"])
        assert "ORDER BY" in cypher

    def test_limit_clause(self):
        cypher, params = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"], limit=10)
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        cypher, params = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"])
        assert "LIMIT" not in cypher
        assert "limit" not in params

    def test_offset_emits_skip(self):
        cypher, params = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"], limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_genes_by_homolog_group(
            group_ids=["cyanorak:CK_1"], limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params


class TestBuildGenesByHomologGroupSummary:
    """Tests for build_genes_by_homolog_group_summary."""

    def test_returns_summary_keys(self):
        cypher, params = build_genes_by_homolog_group_summary(
            group_ids=["cyanorak:CK_1"])
        assert "total_matching" in cypher
        assert "total_genes" in cypher
        assert "total_categories" in cypher
        assert "not_found_groups" in cypher
        assert "not_matched_groups" in cypher
        assert "by_organism" in cypher
        assert "by_category_raw" in cypher
        assert "by_group_raw" in cypher

    def test_organisms_filter(self):
        cypher, params = build_genes_by_homolog_group_summary(
            group_ids=["cyanorak:CK_1"], organisms=["MED4"])
        assert "$organisms IS NULL" in cypher
        assert params["organisms"] == ["MED4"]

    def test_not_found_groups_detection(self):
        cypher, _ = build_genes_by_homolog_group_summary(
            group_ids=["cyanorak:CK_1"])
        assert "OPTIONAL MATCH" in cypher
        assert "not_found_groups" in cypher
        assert "not_matched_groups" in cypher


class TestBuildGenesByHomologGroupDiagnostics:
    """Tests for build_genes_by_homolog_group_diagnostics."""

    def test_returns_expected_keys(self):
        cypher, _ = build_genes_by_homolog_group_diagnostics(
            group_ids=["cyanorak:CK_1"], organisms=["MED4"])
        assert "not_found_organisms" in cypher
        assert "not_matched_organisms" in cypher

    def test_organisms_list_in_params(self):
        cypher, params = build_genes_by_homolog_group_diagnostics(
            group_ids=["cyanorak:CK_1"], organisms=["MED4"])
        assert params["organisms"] == ["MED4"]
        assert params["group_ids"] == ["cyanorak:CK_1"]

    def test_organisms_none_in_params(self):
        cypher, params = build_genes_by_homolog_group_diagnostics(
            group_ids=["cyanorak:CK_1"], organisms=None)
        assert params["organisms"] is None
        assert "not_found_organisms" in cypher


class TestBuildDifferentialExpressionByOrthologGroupCheck:
    """Tests for build_differential_expression_by_ortholog_group_check."""

    def test_returns_not_found(self):
        cypher, params = build_differential_expression_by_ortholog_group_check(
            group_ids=["g1", "g2"],
        )
        assert "OPTIONAL MATCH" in cypher
        assert "not_found" in cypher
        assert params["group_ids"] == ["g1", "g2"]


class TestBuildDifferentialExpressionByOrthologSummaryGlobal:
    """Tests for build_differential_expression_by_ortholog_summary_global."""

    def test_single_group(self):
        cypher, params = build_differential_expression_by_ortholog_summary_global(
            group_ids=["cyanorak:CK_00000570"],
        )
        assert "$group_ids" in cypher
        assert params["group_ids"] == ["cyanorak:CK_00000570"]

    def test_uses_match_not_optional(self):
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["g1"],
        )
        assert "OPTIONAL MATCH" not in cypher
        assert "MATCH (og:OrthologGroup" in cypher

    def test_multiple_groups(self):
        cypher, params = build_differential_expression_by_ortholog_summary_global(
            group_ids=["cyanorak:CK_00000570", "eggnog:COG0592@2"],
        )
        assert len(params["group_ids"]) == 2

    def test_organisms_filter(self):
        cypher, params = build_differential_expression_by_ortholog_summary_global(
            group_ids=["cyanorak:CK_00000570"],
            organisms=["MED4", "MIT9313"],
        )
        assert "$organisms" in cypher
        assert params["organisms"] == ["MED4", "MIT9313"]

    def test_experiment_ids_filter(self):
        cypher, params = build_differential_expression_by_ortholog_summary_global(
            group_ids=["cyanorak:CK_00000570"],
            experiment_ids=["EXP001"],
        )
        assert "$experiment_ids" in cypher
        assert "e.id IN $experiment_ids" in cypher

    def test_direction_filter(self):
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["cyanorak:CK_00000570"],
            direction="up",
        )
        assert "r.expression_status = 'significant_up'" in cypher

    def test_significant_only(self):
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["cyanorak:CK_00000570"],
            significant_only=True,
        )
        assert "r.expression_status <> 'not_significant'" in cypher

    def test_direction_takes_precedence(self):
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["g1"], direction="down", significant_only=True,
        )
        assert "r.expression_status = 'significant_down'" in cypher
        # Direction takes precedence: significant_only's WHERE clause is NOT added
        assert "r.expression_status <> 'not_significant'" not in cypher

    def test_returns_expected_keys(self):
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["g1"],
        )
        for key in ["total_matching", "matching_genes", "matching_groups",
                     "experiment_count", "by_organism", "rows_by_status",
                     "rows_by_treatment_type", "by_table_scope",
                     "sig_log2fcs", "matched_group_ids"]:
            assert key in cypher, f"Missing RETURN key: {key}"


class TestBuildDifferentialExpressionByOrthologTopGroups:
    """Tests for build_differential_expression_by_ortholog_top_groups."""

    def test_returns_top_groups(self):
        cypher, params = build_differential_expression_by_ortholog_top_groups(
            group_ids=["g1", "g2"],
        )
        assert "top_groups" in cypher
        assert "LIMIT 5" in cypher
        assert "ORDER BY significant_genes DESC" in cypher

    def test_filters_applied(self):
        cypher, params = build_differential_expression_by_ortholog_top_groups(
            group_ids=["g1"], direction="up",
        )
        assert "r.expression_status = 'significant_up'" in cypher


class TestBuildDifferentialExpressionByOrthologTopExperiments:
    """Tests for build_differential_expression_by_ortholog_top_experiments."""

    def test_returns_top_experiments(self):
        cypher, params = build_differential_expression_by_ortholog_top_experiments(
            group_ids=["g1"],
        )
        assert "top_experiments" in cypher
        assert "LIMIT 5" in cypher

    def test_filters_applied(self):
        cypher, params = build_differential_expression_by_ortholog_top_experiments(
            group_ids=["g1"], organisms=["MED4"],
        )
        assert "$organisms" in cypher


class TestBuildDifferentialExpressionByOrthologResults:
    """Tests for build_differential_expression_by_ortholog_results."""

    def test_group_x_experiment_x_timepoint_rows(self):
        cypher, params = build_differential_expression_by_ortholog_results(
            group_ids=["g1"],
        )
        for key in ["group_id", "consensus_gene_name", "consensus_product",
                     "experiment_id", "treatment_type", "organism_name",
                     "coculture_partner", "timepoint", "timepoint_hours",
                     "timepoint_order", "genes_with_expression",
                     "significant_up", "significant_down", "not_significant"]:
            assert key in cypher, f"Missing RETURN key: {key}"

    def test_verbose_fields(self):
        cypher, _ = build_differential_expression_by_ortholog_results(
            group_ids=["g1"], verbose=True,
        )
        for key in ["experiment_name", "treatment", "omics_type",
                     "table_scope", "table_scope_detail"]:
            assert key in cypher, f"Missing verbose key: {key}"

    def test_verbose_false_excludes(self):
        cypher, _ = build_differential_expression_by_ortholog_results(
            group_ids=["g1"], verbose=False,
        )
        assert "experiment_name" not in cypher

    def test_limit(self):
        cypher, params = build_differential_expression_by_ortholog_results(
            group_ids=["g1"], limit=10,
        )
        assert "$limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        cypher, params = build_differential_expression_by_ortholog_results(
            group_ids=["g1"], limit=None,
        )
        assert "LIMIT" not in cypher
        assert "limit" not in params

    def test_order_by(self):
        cypher, _ = build_differential_expression_by_ortholog_results(
            group_ids=["g1"],
        )
        assert "ORDER BY" in cypher

    def test_offset_emits_skip(self):
        cypher, params = build_differential_expression_by_ortholog_results(
            group_ids=["g1"], limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
        assert cypher.index("SKIP") < cypher.index("LIMIT")

    def test_offset_zero_no_skip(self):
        cypher, params = build_differential_expression_by_ortholog_results(
            group_ids=["g1"], limit=10, offset=0,
        )
        assert "SKIP" not in cypher
        assert "offset" not in params


class TestBuildDifferentialExpressionByOrthologMembershipCounts:
    """Tests for build_differential_expression_by_ortholog_membership_counts."""

    def test_returns_expected_keys(self):
        cypher, params = build_differential_expression_by_ortholog_membership_counts(
            group_ids=["g1"],
        )
        for key in ["group_id", "organism_name", "total_genes"]:
            assert key in cypher

    def test_organism_filter(self):
        cypher, params = build_differential_expression_by_ortholog_membership_counts(
            group_ids=["g1"], organisms=["MED4"],
        )
        assert "$organisms" in cypher
        assert params["organisms"] == ["MED4"]

    def test_no_expression_edges(self):
        """Membership counts should not reference expression edges."""
        cypher, _ = build_differential_expression_by_ortholog_membership_counts(
            group_ids=["g1"],
        )
        assert "Changes_expression_of" not in cypher
        assert "Experiment" not in cypher


class TestBuildDifferentialExpressionByOrthologDiagnostics:
    """Tests for build_differential_expression_by_ortholog_diagnostics."""

    def test_none_returns_none(self):
        result = build_differential_expression_by_ortholog_diagnostics(
            group_ids=["g1"],
        )
        assert result is None

    def test_organisms_returns_queries(self):
        result = build_differential_expression_by_ortholog_diagnostics(
            group_ids=["g1"], organisms=["MED4"],
        )
        assert result is not None
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_experiment_ids_returns_queries(self):
        result = build_differential_expression_by_ortholog_diagnostics(
            group_ids=["g1"], experiment_ids=["EXP001"],
        )
        assert result is not None
        assert isinstance(result, list)

    def test_combined_filters_no_double_where(self):
        """Combined organisms + experiment_ids must not produce double WHERE."""
        result = build_differential_expression_by_ortholog_diagnostics(
            group_ids=["g1"],
            organisms=["MED4"],
            experiment_ids=["EXP001"],
            direction="up",
        )
        assert result is not None
        for cypher, _ in result:
            # Each WHERE keyword should be followed by conditions, not another WHERE
            parts = cypher.split("WHERE")
            for i, part in enumerate(parts):
                if i == 0:
                    continue
                stripped = part.strip()
                assert not stripped.startswith("WHERE"), (
                    f"Double WHERE found in diagnostic query:\n{cypher}"
                )

    def test_direction_forwarded_to_diagnostics(self):
        """Direction filter must appear in diagnostic Cypher."""
        result = build_differential_expression_by_ortholog_diagnostics(
            group_ids=["g1"], organisms=["MED4"], direction="up",
        )
        assert result is not None
        cypher, _ = result[0]
        assert "r.expression_status = 'significant_up'" in cypher

    def test_significant_only_forwarded_to_diagnostics(self):
        """significant_only filter must appear in diagnostic Cypher."""
        result = build_differential_expression_by_ortholog_diagnostics(
            group_ids=["g1"], experiment_ids=["EXP001"],
            significant_only=True,
        )
        assert result is not None
        cypher, _ = result[0]
        assert "r.expression_status <> 'not_significant'" in cypher


class TestBuildGeneResponseProfileEnvelope:
    def test_basic(self):
        cypher, params = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
        )
        assert "MATCH" in cypher
        assert params["locus_tags"] == ["PMM0370"]
        assert params["organism_name"] == "Prochlorococcus MED4"

    def test_returns_expected_columns(self):
        cypher, _ = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
        )
        for col in ["found_genes", "has_expression", "has_significant"]:
            assert col in cypher

    def test_organism_exact_match(self):
        cypher, params = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
        )
        assert "$organism_name" in cypher

    def test_treatment_types_filter(self):
        cypher, params = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            treatment_types=["nitrogen_stress"],
        )
        assert "$treatment_types" in cypher
        assert params["treatment_types"] == ["nitrogen_stress"]

    def test_experiment_ids_filter(self):
        cypher, params = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            experiment_ids=["exp1"],
        )
        assert "$experiment_ids" in cypher
        assert params["experiment_ids"] == ["exp1"]

    def test_group_by_treatment_type(self):
        cypher, _ = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            group_by="treatment_type",
        )
        assert "treatment_type" in cypher

    def test_group_by_experiment(self):
        cypher, _ = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            group_by="experiment",
        )
        assert ".id" in cypher

    def test_invalid_group_by_raises(self):
        with pytest.raises(ValueError, match="group_by"):
            build_gene_response_profile_envelope(
                locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
                group_by="invalid",
            )

    def test_group_totals_include_table_scopes(self):
        cypher, _ = build_gene_response_profile_envelope(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
        )
        assert "table_scopes" in cypher


class TestBuildGeneResponseProfile:
    def test_basic(self):
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
        )
        assert "MATCH" in cypher
        assert params["locus_tags"] == ["PMM0370"]
        assert params["organism_name"] == "Prochlorococcus MED4"

    def test_returns_expected_columns(self):
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
        )
        for col in [
            "locus_tag", "gene_name", "product", "gene_category",
            "group_key", "experiments_tested", "experiments_up",
            "experiments_down", "timepoints_tested", "timepoints_up",
            "timepoints_down", "rank_ups", "rank_downs",
            "log2fcs_up", "log2fcs_down",
        ]:
            assert col in cypher

    def test_order_by(self):
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
        )
        assert "ORDER BY" in cypher
        assert "groups_responded DESC" in cypher

    def test_skip_limit(self):
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            limit=10, offset=5,
        )
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["offset"] == 5
        assert params["limit"] == 10

    def test_group_by_treatment_type(self):
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            group_by="treatment_type",
        )
        assert "treatment_type" in cypher

    def test_group_by_experiment(self):
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            group_by="experiment",
        )
        assert ".id AS group_key" in cypher or ".id" in cypher

    def test_treatment_types_filter(self):
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            treatment_types=["nitrogen_stress"],
        )
        assert "$treatment_types" in cypher
        assert params["treatment_types"] == ["nitrogen_stress"]

    def test_experiment_ids_filter(self):
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
            experiment_ids=["exp1"],
        )
        assert "$experiment_ids" in cypher
        assert params["experiment_ids"] == ["exp1"]

    def test_invalid_group_by_raises(self):
        with pytest.raises(ValueError, match="group_by"):
            build_gene_response_profile(
                locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
                group_by="invalid",
            )

    def test_no_limit_no_skip(self):
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0370"], organism_name="Prochlorococcus MED4",
        )
        assert "SKIP" not in cypher
        assert "LIMIT" not in cypher


# ---------------------------------------------------------------------------
# ClusteringAnalysis helpers
# ---------------------------------------------------------------------------


class TestClusteringAnalysisWhere:
    """Tests for _clustering_analysis_where shared helper."""

    def test_no_filters(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where()
        assert conditions == []
        assert params == {}

    def test_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(organism="MED4")
        assert len(conditions) == 1
        assert "organism_name" in conditions[0].lower()
        assert params["organism"] == "MED4"

    def test_cluster_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(cluster_type="condition_comparison")
        assert len(conditions) == 1
        assert "$cluster_type" in conditions[0]
        assert params["cluster_type"] == "condition_comparison"

    def test_treatment_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(treatment_type=["nitrogen_stress"])
        assert len(conditions) == 1
        assert "ANY(" in conditions[0]
        assert "$treatment_type" in conditions[0]
        assert params["treatment_type"] == ["nitrogen_stress"]

    def test_omics_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(omics_type="MICROARRAY")
        assert len(conditions) == 1
        assert "$omics_type" in conditions[0]
        assert params["omics_type"] == "MICROARRAY"

    def test_background_factors_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(
            background_factors=["axenic"])
        assert len(conditions) == 1
        assert "ANY(" in conditions[0]
        assert "background_factors" in conditions[0]
        assert params["background_factors"] == ["axenic"]

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(
            organism="MED4", cluster_type="condition_comparison",
            treatment_type=["nitrogen_stress"], omics_type="MICROARRAY",
            background_factors=["axenic"],
        )
        assert len(conditions) == 5
        assert len(params) == 5


class TestBuildListClusteringAnalysesSummary:
    """Tests for build_list_clustering_analyses_summary."""

    def test_no_search_no_filters(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary()
        assert "ClusteringAnalysis" in cypher
        assert "total_entries" in cypher
        assert "total_matching" in cypher
        assert "by_organism" in cypher
        assert "by_cluster_type" in cypher
        assert "by_treatment_type" in cypher
        assert "by_background_factors" in cypher
        assert "by_omics_type" in cypher
        assert "WHERE" not in cypher

    def test_with_search_text(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(search_text="nitrogen")
        assert "clusteringAnalysisFullText" in cypher
        assert params["search_text"] == "nitrogen"
        assert "score_max" in cypher
        assert "score_median" in cypher

    def test_with_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(organism="MED4")
        assert "WHERE" in cypher
        assert params["organism"] == "MED4"

    def test_with_publication_doi_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(
            publication_doi=["10.1038/msb4100087"])
        assert "PublicationHasClusteringAnalysis" in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]

    def test_with_experiment_ids_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(
            experiment_ids=["10.1038/msb4100087_n_starvation_med4"])
        assert "ExperimentHasClusteringAnalysis" in cypher
        assert params["experiment_ids"] == ["10.1038/msb4100087_n_starvation_med4"]

    def test_with_analysis_ids_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(
            analysis_ids=["clustering_analysis:msb4100087:med4_kmeans_nstarvation"])
        assert "$analysis_ids" in cypher
        assert params["analysis_ids"] == ["clustering_analysis:msb4100087:med4_kmeans_nstarvation"]


class TestBuildListClusteringAnalyses:
    """Tests for build_list_clustering_analyses (detail builder)."""

    def test_no_search_returns_expected_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses()
        for col in ["analysis_id", "name", "organism_name", "cluster_method",
                     "cluster_type", "cluster_count", "total_gene_count",
                     "treatment_type", "background_factors", "omics_type"]:
            assert f"AS {col}" in cypher, f"Missing column: {col}"
        assert "score" not in cypher
        # Inline clusters via subquery
        assert "ClusteringAnalysisHasGeneCluster" in cypher

    def test_with_search_text(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(search_text="nitrogen")
        assert "clusteringAnalysisFullText" in cypher
        assert "score" in cypher
        assert params["search_text"] == "nitrogen"

    def test_verbose_adds_analysis_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=True)
        for col in ["treatment", "light_condition", "experimental_context"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"

    def test_verbose_false_omits_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=False)
        assert "ca.treatment AS treatment" not in cypher
        assert "AS light_condition" not in cypher

    def test_verbose_adds_cluster_descriptions(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=True)
        assert "functional_description" in cypher
        assert "expression_dynamics" in cypher
        assert "temporal_pattern" in cypher

    def test_inline_clusters_compact(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=False)
        # Compact clusters: id, name, member_count
        assert "cluster_id" in cypher or "gc.id" in cypher
        assert "member_count" in cypher

    def test_experiment_ids_optional_match(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses()
        # Experiment IDs should be OPTIONAL MATCH (may not exist)
        assert "OPTIONAL MATCH" in cypher
        assert "ExperimentHasClusteringAnalysis" in cypher

    def test_publication_doi_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(
            publication_doi=["10.1038/msb4100087"])
        assert "PublicationHasClusteringAnalysis" in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]

    def test_offset_emits_skip(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5

    def test_offset_zero_no_skip(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(limit=10, offset=0)
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_has_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, _ = build_list_clustering_analyses()
        assert "ORDER BY" in cypher


# ---------------------------------------------------------------------------
# gene_clusters_by_gene (via ClusteringAnalysis)
# ---------------------------------------------------------------------------
class TestBuildGeneClustersByGeneSummary:
    """Tests for build_gene_clusters_by_gene_summary."""

    def test_basic_structure(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370", "PMM0920"])
        assert "Gene_in_gene_cluster" in cypher
        assert "GeneCluster" in cypher
        assert "ClusteringAnalysisHasGeneCluster" in cypher
        assert "ClusteringAnalysis" in cypher
        assert "total_matching" in cypher
        assert "total_clusters" in cypher
        assert "not_found" in cypher or "nf" in cypher
        assert "by_analysis" in cypher
        assert params["locus_tags"] == ["PMM0370", "PMM0920"]

    def test_no_publication_has_gene_cluster(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, _ = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"])
        assert "Publication_has_gene_cluster" not in cypher

    def test_with_cluster_type_filter_on_ca(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"], cluster_type="stress_response")
        assert "$cluster_type" in cypher
        assert "ca.cluster_type" in cypher
        assert params["cluster_type"] == "stress_response"

    def test_with_treatment_type_filter_on_ca(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"], treatment_type=["nitrogen_stress"])
        assert "$treatment_type" in cypher
        assert "ca.treatment_type" in cypher
        assert params["treatment_type"] == ["nitrogen_stress"]

    def test_with_background_factors_filter_on_ca(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"], background_factors=["axenic"])
        assert "$background_factors" in cypher
        assert "ca.background_factors" in cypher
        assert params["background_factors"] == ["axenic"]

    def test_with_analysis_ids_filter(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"],
            analysis_ids=["clustering_analysis:msb4100087:med4_kmeans"])
        assert "$analysis_ids" in cypher
        assert "ca.id IN $analysis_ids" in cypher
        assert params["analysis_ids"] == ["clustering_analysis:msb4100087:med4_kmeans"]

    def test_with_publication_doi_filter_via_ca(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"],
            publication_doi=["10.1038/msb4100087"])
        assert "PublicationHasClusteringAnalysis" in cypher
        assert "Publication_has_gene_cluster" not in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]


class TestBuildGeneClustersByGene:
    """Tests for build_gene_clusters_by_gene (detail builder)."""

    def test_returns_expected_compact_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, params = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"])
        for col in ["locus_tag", "gene_name", "cluster_id",
                     "cluster_name", "cluster_type",
                     "membership_score", "analysis_id", "analysis_name",
                     "treatment_type", "background_factors"]:
            assert f"AS {col}" in cypher, f"Missing compact column: {col}"

    def test_compact_cluster_type_from_ca(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"])
        assert "ca.cluster_type AS cluster_type" in cypher

    def test_no_source_paper(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=True)
        assert "source_paper" not in cypher

    def test_uses_clustering_analysis_join(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"])
        assert "ClusteringAnalysisHasGeneCluster" in cypher
        assert "Publication_has_gene_cluster" not in cypher

    def test_verbose_adds_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=True)
        for col in ["cluster_functional_description",
                     "cluster_expression_dynamics",
                     "cluster_temporal_pattern",
                     "cluster_method", "member_count",
                     "treatment", "light_condition",
                     "experimental_context", "p_value"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"

    def test_verbose_false_omits_verbose_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=False)
        assert "cluster_functional_description" not in cypher
        assert "cluster_expression_dynamics" not in cypher
        assert "cluster_method" not in cypher

    def test_analysis_ids_filter(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, params = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"],
            analysis_ids=["clustering_analysis:msb4100087:med4_kmeans"])
        assert "ca.id IN $analysis_ids" in cypher
        assert params["analysis_ids"] == ["clustering_analysis:msb4100087:med4_kmeans"]

    def test_publication_doi_filter_via_ca(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, params = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"],
            publication_doi=["10.1038/msb4100087"])
        assert "PublicationHasClusteringAnalysis" in cypher
        assert "Publication_has_gene_cluster" not in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]

    def test_offset_emits_skip(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, params = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5

    def test_has_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(locus_tags=["PMM0370"])
        assert "ORDER BY" in cypher


# ---------------------------------------------------------------------------
# genes_in_cluster (with analysis_id support)
# ---------------------------------------------------------------------------
class TestBuildGenesInClusterSummary:
    """Tests for build_genes_in_cluster_summary."""

    def test_basic_structure_cluster_ids(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster_summary
        cypher, params = build_genes_in_cluster_summary(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        assert "Gene_in_gene_cluster" in cypher
        assert "total_matching" in cypher
        assert "not_found_clusters" in cypher or "nf" in cypher
        assert params["cluster_ids"] == ["cluster:msb4100087:med4:up_n_transport"]

    def test_with_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster_summary
        cypher, params = build_genes_in_cluster_summary(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            organism="MED4")
        assert "organism" in cypher.lower()
        assert params["organism"] == "MED4"

    def test_analysis_id_mode(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster_summary
        cypher, params = build_genes_in_cluster_summary(
            analysis_id="clustering_analysis:msb4100087:med4_kmeans")
        assert "ClusteringAnalysis" in cypher
        assert "ClusteringAnalysisHasGeneCluster" in cypher
        assert "$analysis_id" in cypher
        assert "analysis_name" in cypher
        assert params["analysis_id"] == "clustering_analysis:msb4100087:med4_kmeans"


class TestBuildGenesInCluster:
    """Tests for build_genes_in_cluster (detail builder)."""

    def test_returns_expected_columns(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        for col in ["locus_tag", "gene_name", "product", "gene_category",
                     "organism_name", "cluster_id", "cluster_name",
                     "membership_score"]:
            assert f"AS {col}" in cypher

    def test_verbose_renamed_columns(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            verbose=True)
        for col in ["gene_function_description", "gene_summary",
                     "p_value", "cluster_functional_description",
                     "cluster_expression_dynamics",
                     "cluster_temporal_pattern"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"
        # Old column names must NOT appear
        assert "AS function_description" not in cypher
        assert "AS functional_description" not in cypher.replace(
            "cluster_functional_description", "")
        assert "AS expression_dynamics" not in cypher.replace(
            "cluster_expression_dynamics", "")

    def test_analysis_id_mode(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, params = build_genes_in_cluster(
            analysis_id="clustering_analysis:msb4100087:med4_kmeans")
        assert "ClusteringAnalysis" in cypher
        assert "ClusteringAnalysisHasGeneCluster" in cypher
        assert "$analysis_id" in cypher
        assert params["analysis_id"] == "clustering_analysis:msb4100087:med4_kmeans"

    def test_has_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        assert "ORDER BY" in cypher

    def test_offset_emits_skip(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, params = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5


class TestTreatmentTypeArrayFilter:
    """treatment_type is now an array property — filters must use ANY()."""

    def test_list_experiments_uses_any_for_treatment_type(self):
        """treatment_type is now an array — filter must use ANY()."""
        cypher, params = build_list_experiments(
            treatment_type=["coculture", "nitrogen_stress"]
        )
        assert "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)" in cypher
        assert "toLower(e.treatment_type) IN" not in cypher
        assert params["treatment_types"] == ["coculture", "nitrogen_stress"]

    def test_list_experiments_summary_uses_any_for_treatment_type(self):
        cypher, params = build_list_experiments_summary(
            treatment_type=["coculture"]
        )
        assert "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)" in cypher
        assert params["treatment_types"] == ["coculture"]

    def test_gene_response_profile_uses_any_for_treatment_types(self):
        """gene_response_profile filter must also use ANY() for array treatment_type."""
        cypher, params = build_gene_response_profile(
            locus_tags=["PMM0001"],
            organism_name="Prochlorococcus MED4",
            treatment_types=["nitrogen_stress"],
        )
        assert "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)" in cypher
        assert params["treatment_types"] == ["nitrogen_stress"]

    def test_list_experiments_summary_flattens_treatment_type(self):
        """Summary must flatten array treatment_type before frequencies."""
        cypher, _ = build_list_experiments_summary()
        assert "apoc.coll.flatten(collect(coalesce(e.treatment_type, [])))" in cypher
        assert "collect(e.treatment_type) AS tts" not in cypher

    def test_de_by_gene_summary_flattens_treatment_type(self):
        """DE summary must flatten array treatment_type."""
        cypher, _ = build_differential_expression_by_gene_summary_global()
        assert "apoc.coll.flatten(collect(coalesce(e.treatment_type, [])))" in cypher

    def test_de_by_ortholog_summary_flattens_treatment_type(self):
        """DE by ortholog summary must flatten array treatment_type."""
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["OG_test"],
        )
        assert "apoc.coll.flatten(" in cypher
        assert "rows_by_treatment_type" in cypher

    def test_gene_response_profile_group_by_treatment_type_unwinds(self):
        """group_by=treatment_type must UNWIND array to produce one row per value."""
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0001"],
            organism_name="Prochlorococcus MED4",
            group_by="treatment_type",
        )
        assert "UNWIND" in cypher
        assert "_tt AS group_key" in cypher

    def test_gene_response_profile_group_by_experiment_no_unwind(self):
        """group_by=experiment should NOT add UNWIND."""
        cypher, _ = build_gene_response_profile(
            locus_tags=["PMM0001"],
            organism_name="Prochlorococcus MED4",
            group_by="experiment",
        )
        assert "UNWIND" not in cypher
        assert "e.id AS group_key" in cypher

    def test_gene_response_profile_envelope_unwinds_for_treatment_type(self):
        """Envelope query should UNWIND for treatment_type group_by."""
        cypher, _ = build_gene_response_profile_envelope(
            locus_tags=["PMM0001"],
            organism_name="Prochlorococcus MED4",
            group_by="treatment_type",
        )
        assert "UNWIND" in cypher
        assert "_tt AS group_key" in cypher


class TestBackgroundFactors:
    """Tests for background_factors filter, return, and aggregation across builders."""

    def test_list_experiments_returns_background_factors(self):
        cypher, _ = build_list_experiments()
        assert "background_factors" in cypher

    def test_list_experiments_filter(self):
        cypher, params = build_list_experiments(background_factors=["axenic"])
        assert "ANY(bf IN coalesce(e.background_factors, []) WHERE toLower(bf) IN $background_factors)" in cypher
        assert params["background_factors"] == ["axenic"]

    def test_list_experiments_summary_has_by_background_factors(self):
        cypher, _ = build_list_experiments_summary()
        assert "by_background_factors" in cypher

    def test_list_organisms_returns_background_factors(self):
        cypher, _ = build_list_organisms()
        assert "background_factors" in cypher

    def test_list_publications_returns_background_factors(self):
        cypher, _ = build_list_publications()
        assert "background_factors" in cypher

    def test_list_publications_search_returns_background_factors(self):
        cypher, _ = build_list_publications(search_text="light")
        assert "background_factors" in cypher

    def test_list_clustering_analyses_returns_background_factors(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, _ = build_list_clustering_analyses()
        assert "background_factors" in cypher

    def test_list_clustering_analyses_summary_has_by_background_factors(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, _ = build_list_clustering_analyses_summary()
        assert "by_background_factors" in cypher

    def test_differential_expression_by_gene_verbose_has_background_factors(self):
        cypher, _ = build_differential_expression_by_gene(verbose=True)
        assert "background_factors" in cypher

    def test_differential_expression_by_gene_compact_no_background_factors(self):
        cypher, _ = build_differential_expression_by_gene(verbose=False)
        assert "background_factors" not in cypher

    def test_differential_expression_by_gene_summary_by_experiment_has_background_factors(self):
        cypher, _ = build_differential_expression_by_gene_summary_by_experiment()
        assert "background_factors" in cypher

    def test_differential_expression_by_ortholog_top_experiments_has_background_factors(self):
        cypher, _ = build_differential_expression_by_ortholog_top_experiments(
            group_ids=["OG_1"]
        )
        assert "background_factors" in cypher

    def test_differential_expression_by_ortholog_results_has_background_factors(self):
        cypher, _ = build_differential_expression_by_ortholog_results(
            group_ids=["OG_1"]
        )
        assert "background_factors" in cypher


class TestGrowthPhases:
    """Tests for growth_phases filter, return, and aggregation across builders."""

    # --- Publications ---

    def test_list_publications_returns_growth_phases(self):
        """Returns growth_phases column."""
        cypher, _ = build_list_publications()
        assert "growth_phases" in cypher

    def test_list_publications_search_returns_growth_phases(self):
        """search_text variant also returns growth_phases."""
        cypher, _ = build_list_publications(search_text="light")
        assert "growth_phases" in cypher

    def test_list_publications_growth_phases_filter(self):
        """growth_phases filter adds ANY-match condition."""
        cypher, params = build_list_publications(growth_phases="exponential")
        assert "growth_phases" in cypher
        assert "growth_phases" in params

    def test_list_publications_growth_phases_filter_cypher(self):
        """growth_phases filter uses ANY on coalesce(p.growth_phases, []) with toLower."""
        cypher, params = build_list_publications(growth_phases="exponential")
        assert "ANY(gp IN coalesce(p.growth_phases, [])" in cypher
        assert "toLower(gp) = toLower($growth_phases)" in cypher
        assert params["growth_phases"] == "exponential"

    def test_list_publications_growth_phases_none_no_filter(self):
        """growth_phases=None does not add filter."""
        cypher, _ = build_list_publications(growth_phases=None)
        assert "$growth_phases" not in cypher

    def test_list_publications_summary_accepts_growth_phases(self):
        """Summary builder threads growth_phases through to where clause."""
        cypher, params = build_list_publications_summary(growth_phases="exponential")
        assert "growth_phases" in cypher
        assert params["growth_phases"] == "exponential"

    # --- Organisms ---

    def test_list_organisms_returns_growth_phases(self):
        """Returns growth_phases column."""
        cypher, _ = build_list_organisms()
        assert "growth_phases" in cypher

    # --- Clustering ---

    def test_list_clustering_analyses_returns_growth_phases(self):
        """Returns growth_phases column."""
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, _ = build_list_clustering_analyses()
        assert "growth_phases" in cypher

    def test_list_clustering_analyses_growth_phases_filter(self):
        """growth_phases filter adds ANY-match condition."""
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(growth_phases=["diel"])
        assert "growth_phases" in cypher
        assert "growth_phases" in params

    def test_list_clustering_analyses_growth_phases_filter_cypher(self):
        """growth_phases filter uses ANY on coalesce(ca.growth_phases, []) with lowercased list."""
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses, _clustering_analysis_where
        conditions, params = _clustering_analysis_where(growth_phases=["Diel", "Exponential"])
        assert any("growth_phases" in c for c in conditions)
        assert params["growth_phases"] == ["diel", "exponential"]

    def test_list_clustering_analyses_growth_phases_none_no_filter(self):
        """growth_phases=None does not add filter."""
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, _ = build_list_clustering_analyses(growth_phases=None)
        assert "$growth_phases" not in cypher

    def test_list_clustering_analyses_summary_returns_by_growth_phase(self):
        """Summary includes by_growth_phase breakdown."""
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, _ = build_list_clustering_analyses_summary()
        assert "by_growth_phase" in cypher

    # --- list_filter_values: growth_phase ---

    def test_build_list_growth_phases(self):
        """build_list_growth_phases returns phase and experiment_count."""
        cypher, params = build_list_growth_phases()
        assert "r.growth_phase" in cypher
        assert "experiment_count" in cypher
        assert params == {}


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------


def test_all_ontologies_matches_config_keys():
    assert set(ALL_ONTOLOGIES) == set(ONTOLOGY_CONFIG.keys())
    assert ALL_ONTOLOGIES == [
        "go_bp", "go_mf", "go_cc", "ec", "kegg",
        "cog_category", "cyanorak_role", "tigr_role", "pfam",
        "brite", "tcdb", "cazy",
    ]


def test_go_ontologies_subset_of_all():
    assert GO_ONTOLOGIES <= set(ALL_ONTOLOGIES)
    assert GO_ONTOLOGIES == {"go_bp", "go_mf", "go_cc"}


# ---------------------------------------------------------------------------
# build_ontology_landscape
# ---------------------------------------------------------------------------


class TestBuildOntologyLandscape:
    def test_non_verbose_returns_stats_columns_only(self):
        cypher, params = build_ontology_landscape(
            ontology="cyanorak_role", organism_name="Prochlorococcus MED4",
        )
        assert params == {
            "org": "Prochlorococcus MED4",
            "min_gene_set_size": 5,
            "max_gene_set_size": 500,
        }
        # RETURN columns
        for col in [
            "level", "n_terms_with_genes", "n_genes_at_level",
            "min_genes_per_term", "q1_genes_per_term",
            "median_genes_per_term", "q3_genes_per_term",
            "max_genes_per_term", "n_best_effort",
        ]:
            assert col in cypher, f"missing RETURN column: {col}"
        # Not verbose → no example_terms
        assert "example_terms" not in cypher
        assert "ORDER BY n_g_per_term DESC" not in cypher
        assert "ORDER BY level" in cypher
        # Filter clause present
        assert "$min_gene_set_size" in cypher
        assert "$max_gene_set_size" in cypher

    def test_uses_ontology_config_edge_and_label(self):
        cypher, _ = build_ontology_landscape(
            ontology="go_bp", organism_name="Prochlorococcus MED4",
        )
        assert ":Gene_involved_in_biological_process" in cypher
        assert ":BiologicalProcess" in cypher
        assert "Biological_process_is_a_biological_process" in cypher
        assert "Biological_process_part_of_biological_process" in cypher

    def test_flat_ontology_omits_hierarchy_walk(self):
        """tigr_role has empty hierarchy_rels — only one MATCH."""
        cypher, _ = build_ontology_landscape(
            ontology="tigr_role", organism_name="Prochlorococcus MED4",
        )
        # No hierarchy-walk MATCH (the second MATCH line is absent)
        assert cypher.count("MATCH") == 1
        assert "*0.." not in cypher

    def test_pfam_walks_cross_label_hierarchy_via_helper(self):
        """pfam is 2-level: Pfam leaf (level=1) + PfamClan parent (level=0).

        Post-helper refactor, landscape walks Pfam_in_pfam_clan *0..1 so
        stats surface both levels.
        """
        cypher, _ = build_ontology_landscape(
            ontology="pfam", organism_name="Prochlorococcus MED4",
        )
        assert ":Gene_has_pfam" in cypher
        assert "(leaf:Pfam)" in cypher
        assert "Pfam_in_pfam_clan*0..1" in cypher
        assert "(t:Pfam OR t:PfamClan)" in cypher

    def test_invalid_ontology_raises(self):
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_ontology_landscape(
                ontology="NOT_REAL", organism_name="Prochlorococcus MED4",
            )

    def test_brite_uses_2hop_bridge(self):
        cypher, _ = build_ontology_landscape(
            ontology="brite", organism_name="Prochlorococcus MED4",
        )
        # 2-hop bind
        assert ":Gene_has_kegg_ko" in cypher
        assert ":KeggTerm" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert "(leaf:BriteCategory)" in cypher
        # Hierarchy walk
        assert "Brite_category_is_a_brite_category*0.." in cypher
        assert "(t:BriteCategory)" in cypher
        # Two MATCH clauses (bind + walk)
        assert cypher.count("MATCH") == 2

    def test_verbose_adds_example_terms_and_pre_sort(self):
        cypher, _ = build_ontology_landscape(
            ontology="go_bp", organism_name="Prochlorococcus MED4",
            verbose=True,
        )
        assert "ORDER BY n_g_per_term DESC" in cypher
        assert "[0..3] AS example_terms" in cypher
        assert "example_terms" in cypher.split("RETURN", 1)[1]  # in RETURN

    def test_returns_tree_columns(self):
        cypher, _ = build_ontology_landscape(
            ontology="brite", organism_name="Test Org",
        )
        assert "t.tree AS tree" in cypher
        assert "t.tree_code AS tree_code" in cypher

    def test_groups_by_tree(self):
        cypher, _ = build_ontology_landscape(
            ontology="brite", organism_name="Test Org",
        )
        # Tree should be in grouping WITH clause
        assert "tree" in cypher

    def test_tree_filter(self):
        cypher, params = build_ontology_landscape(
            ontology="brite", organism_name="Test Org",
            tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"

    def test_tree_non_brite_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_ontology_landscape(
                ontology="go_bp", organism_name="Test Org",
                tree="transporters",
            )

    def test_tcdb_uses_label_and_edge(self):
        cypher, _ = build_ontology_landscape(
            ontology="tcdb", organism_name="Prochlorococcus MED4",
        )
        assert ":Gene_has_tcdb_family" in cypher
        assert ":TcdbFamily" in cypher
        assert "Tcdb_family_is_a_tcdb_family" in cypher

    def test_cazy_uses_label_and_edge(self):
        cypher, _ = build_ontology_landscape(
            ontology="cazy", organism_name="Prochlorococcus MED4",
        )
        assert ":Gene_has_cazy_family" in cypher
        assert ":CazyFamily" in cypher
        assert "Cazy_family_is_a_cazy_family" in cypher

    def test_tcdb_tree_filter_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_ontology_landscape(
                ontology="tcdb", organism_name="Test Org",
                tree="transporters",
            )

    def test_cazy_tree_filter_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_ontology_landscape(
                ontology="cazy", organism_name="Test Org",
                tree="Enzymes",
            )


# ---------------------------------------------------------------------------
# build_ontology_expcov
# ---------------------------------------------------------------------------


class TestBuildOntologyExpcov:
    def test_returns_per_eid_level_coverage(self):
        cypher, params = build_ontology_expcov(
            ontology="cyanorak_role",
            organism_name="Prochlorococcus MED4",
            experiment_ids=["e1", "e2"],
        )
        assert params == {
            "org": "Prochlorococcus MED4",
            "experiment_ids": ["e1", "e2"],
            "min_gene_set_size": 5,
            "max_gene_set_size": 500,
        }
        assert "UNWIND $experiment_ids AS eid" in cypher
        assert "Changes_expression_of" in cypher
        for col in ["eid", "n_total", "level", "n_at_level"]:
            assert col in cypher
        assert "ORDER BY eid, level" in cypher
        # Filter clause present (same filter as Q_landscape for consistency)
        assert "$min_gene_set_size" in cypher
        assert "$max_gene_set_size" in cypher

    def test_flat_ontology_omits_hierarchy_walk(self):
        cypher, _ = build_ontology_expcov(
            ontology="tigr_role",
            organism_name="Prochlorococcus MED4",
            experiment_ids=["e1"],
        )
        assert "*0.." not in cypher

    def test_invalid_ontology_raises(self):
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_ontology_expcov(
                ontology="bogus",
                organism_name="Prochlorococcus MED4",
                experiment_ids=["e1"],
            )

    def test_brite_uses_2hop_bridge(self):
        cypher, _ = build_ontology_expcov(
            ontology="brite",
            organism_name="Prochlorococcus MED4",
            experiment_ids=["e1"],
        )
        assert ":Gene_has_kegg_ko" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert "(leaf:BriteCategory)" in cypher
        assert "Brite_category_is_a_brite_category*0.." in cypher

    def test_asserts_when_hierarchy_walk_prefix_changes(self, monkeypatch):
        from multiomics_explorer.kg import queries_lib

        monkeypatch.setattr(
            queries_lib, "_hierarchy_walk",
            lambda *a, **kw: {"bind_up": "MATCH (g:Gene)", "walk_up": ""},
        )
        with pytest.raises(AssertionError, match="_hierarchy_walk bind_up format"):
            build_ontology_expcov(
                ontology="pfam",
                organism_name="MED4",
                experiment_ids=["e1"],
            )


# ---------------------------------------------------------------------------
# build_ontology_experiment_check
# ---------------------------------------------------------------------------


class TestBuildOntologyExperimentCheck:
    def test_returns_exists_and_exp_organism_per_eid(self):
        cypher, params = build_ontology_experiment_check(
            experiment_ids=["a", "b"],
        )
        assert params == {"experiment_ids": ["a", "b"]}
        assert "UNWIND $experiment_ids AS eid" in cypher
        assert "OPTIONAL MATCH (e:Experiment {id: eid})" in cypher
        for col in ["eid", "exists", "exp_organism"]:
            assert col in cypher


# ---------------------------------------------------------------------------
# build_ontology_organism_gene_count
# ---------------------------------------------------------------------------


class TestBuildOntologyOrganismGeneCount:
    def test_returns_single_count(self):
        cypher, params = build_ontology_organism_gene_count(
            organism_name="Prochlorococcus MED4",
        )
        assert params == {"org": "Prochlorococcus MED4"}
        assert "MATCH (g:Gene {organism_name:$org})" in cypher
        assert "count(g)" in cypher
        assert "AS total_genes" in cypher


# ---------------------------------------------------------------------------
# TestDEGrowthPhases
# ---------------------------------------------------------------------------


class TestDEGrowthPhases:
    """growth_phase integration across DE builders."""

    def test_de_by_gene_growth_phases_filter(self):
        """Edge-level growth_phases filter on r.growth_phase."""
        cypher, params = build_differential_expression_by_gene(
            organism="MED4", growth_phases=["exponential"]
        )
        assert "r.growth_phase" in cypher
        assert params["growth_phases"] == ["exponential"]

    def test_de_by_gene_returns_growth_phase(self):
        """Returns growth_phase column from edge."""
        cypher, _ = build_differential_expression_by_gene(organism="MED4")
        assert "r.growth_phase AS growth_phase" in cypher

    def test_de_by_gene_summary_global_rows_by_growth_phase(self):
        """Summary includes rows_by_growth_phase."""
        cypher, _ = build_differential_expression_by_gene_summary_global(
            organism="MED4"
        )
        assert "rows_by_growth_phase" in cypher

    def test_de_by_gene_summary_by_experiment_growth_phase(self):
        """Per-experiment summary includes growth_phase at timepoint level."""
        cypher, _ = build_differential_expression_by_gene_summary_by_experiment(
            organism="MED4"
        )
        assert "growth_phase" in cypher

    def test_de_by_ortholog_growth_phases_filter(self):
        """Edge-level growth_phases filter in ortholog DE."""
        cypher, params = build_differential_expression_by_ortholog_results(
            group_ids=["OG1"], growth_phases=["diel"]
        )
        assert "r.growth_phase" in cypher
        assert params["growth_phases"] == ["diel"]

    def test_de_by_ortholog_results_returns_growth_phase(self):
        """Ortholog results include growth_phase column."""
        cypher, _ = build_differential_expression_by_ortholog_results(
            group_ids=["OG1"]
        )
        assert "growth_phase" in cypher

    def test_de_by_ortholog_summary_global_rows_by_growth_phase(self):
        """Ortholog summary includes rows_by_growth_phase."""
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["OG1"]
        )
        assert "rows_by_growth_phase" in cypher


class TestListDerivedMetricsWhere:
    """Tests for the shared WHERE-clause helper."""

    def test_no_filters_returns_empty(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where()
        assert conditions == []
        assert params == {}

    def test_organism_space_split_contains(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(organism="MED4")
        assert len(conditions) == 1
        assert "ALL(word IN split(toLower($organism), ' ')" in conditions[0]
        assert "toLower(dm.organism_name) CONTAINS word" in conditions[0]
        assert params == {"organism": "MED4"}

    def test_metric_types_list(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(
            metric_types=["damping_ratio", "peak_time_protein_h"])
        assert conditions == ["dm.metric_type IN $metric_types"]
        assert params == {"metric_types": ["damping_ratio", "peak_time_protein_h"]}

    def test_value_kind(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(value_kind="numeric")
        assert conditions == ["dm.value_kind = $value_kind"]
        assert params == {"value_kind": "numeric"}

    def test_compartment(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(compartment="whole_cell")
        assert conditions == ["dm.compartment = $compartment"]
        assert params == {"compartment": "whole_cell"}

    def test_omics_type_upper(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(omics_type="rnaseq")
        assert conditions == ["toUpper(dm.omics_type) = $omics_type_upper"]
        assert params == {"omics_type_upper": "RNASEQ"}

    def test_treatment_type_any_lowered(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(treatment_type=["Diel", "DARKNESS"])
        assert len(conditions) == 1
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in conditions[0]
        assert "toLower(t) IN $treatment_types_lower" in conditions[0]
        assert params == {"treatment_types_lower": ["diel", "darkness"]}

    def test_background_factors_any_lowered_null_safe(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(background_factors=["Axenic"])
        assert len(conditions) == 1
        assert "ANY(bf IN coalesce(dm.background_factors, [])" in conditions[0]
        assert params == {"background_factors_lower": ["axenic"]}

    def test_growth_phases_any_lowered(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(growth_phases=["Darkness"])
        assert len(conditions) == 1
        assert "ANY(gp IN coalesce(dm.growth_phases, [])" in conditions[0]
        assert params == {"growth_phases_lower": ["darkness"]}

    def test_publication_doi_list(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(
            publication_doi=["10.1128/mSystems.00040-18"])
        assert conditions == ["dm.publication_doi IN $publication_doi"]
        assert params == {"publication_doi": ["10.1128/mSystems.00040-18"]}

    def test_experiment_ids_list(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(experiment_ids=["exp_1"])
        assert conditions == ["dm.experiment_id IN $experiment_ids"]
        assert params == {"experiment_ids": ["exp_1"]}

    def test_derived_metric_ids_list(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(derived_metric_ids=["dm:1", "dm:2"])
        assert conditions == ["dm.id IN $derived_metric_ids"]
        assert params == {"derived_metric_ids": ["dm:1", "dm:2"]}

    def test_rankable_true_coerces_to_string(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(rankable=True)
        assert conditions == ["dm.rankable = $rankable_str"]
        assert params == {"rankable_str": "true"}

    def test_rankable_false_coerces_to_string(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(rankable=False)
        assert conditions == ["dm.rankable = $rankable_str"]
        assert params == {"rankable_str": "false"}

    def test_has_p_value_coerces_to_string(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        _, params_true = _list_derived_metrics_where(has_p_value=True)
        _, params_false = _list_derived_metrics_where(has_p_value=False)
        assert params_true == {"has_p_value_str": "true"}
        assert params_false == {"has_p_value_str": "false"}

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(
            organism="NATL2A", value_kind="boolean", rankable=False)
        assert len(conditions) == 3
        assert params.keys() == {"organism", "value_kind", "rankable_str"}


class TestBuildListDerivedMetricsSummary:
    """Tests for build_list_derived_metrics_summary."""

    def test_no_filters_no_search(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, params = build_list_derived_metrics_summary()
        assert "MATCH (dm:DerivedMetric)" in cypher
        assert "CALL db.index.fulltext.queryNodes" not in cypher
        assert "WHERE" not in cypher
        assert "count(dm) AS total_matching" in cypher
        assert "apoc.coll.frequencies(organisms) AS by_organism" in cypher
        assert "apoc.coll.frequencies(value_kinds) AS by_value_kind" in cypher
        assert "apoc.coll.frequencies(metric_types) AS by_metric_type" in cypher
        assert "apoc.coll.frequencies(compartments) AS by_compartment" in cypher
        assert "apoc.coll.frequencies(omics_types) AS by_omics_type" in cypher
        assert (
            "apoc.coll.frequencies(treatment_types_flat) AS by_treatment_type"
            in cypher
        )
        assert (
            "apoc.coll.frequencies(background_factors_flat) AS by_background_factors"
            in cypher
        )
        assert (
            "apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase"
            in cypher
        )
        assert "MATCH (all_dm:DerivedMetric) RETURN count(all_dm) AS total_entries" in cypher
        assert params == {}
        assert "score_max" not in cypher
        assert "score_median" not in cypher

    def test_search_text_uses_fulltext_index(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, params = build_list_derived_metrics_summary(search_text="diel")
        assert (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)"
            in cypher
        )
        assert "YIELD node AS dm, score" in cypher
        assert "max(score) AS score_max" in cypher
        assert "percentileDisc(score, 0.5) AS score_median" in cypher
        assert params == {"search_text": "diel"}

    def test_shares_where_clause(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, params = build_list_derived_metrics_summary(
            organism="MED4", value_kind="numeric", rankable=True)
        assert "WHERE" in cypher
        assert "dm.value_kind = $value_kind" in cypher
        assert "dm.rankable = $rankable_str" in cypher
        assert params == {
            "organism": "MED4",
            "value_kind": "numeric",
            "rankable_str": "true",
        }

    def test_null_safe_flatten(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, _ = build_list_derived_metrics_summary()
        # All three list-typed aggregations must tolerate null via coalesce(..., [])
        assert "apoc.coll.flatten(collect(coalesce(dm.treatment_type, [])))" in cypher
        assert "apoc.coll.flatten(collect(coalesce(dm.background_factors, [])))" in cypher
        assert "apoc.coll.flatten(collect(coalesce(dm.growth_phases, [])))" in cypher

    def test_search_text_with_filters(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, params = build_list_derived_metrics_summary(
            search_text="diel", organism="MED4", value_kind="numeric")
        # Both fulltext MATCH and WHERE present
        assert (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)"
            in cypher
        )
        assert "WHERE" in cypher
        assert "dm.value_kind = $value_kind" in cypher
        # WHERE clause must come AFTER the YIELD line
        assert cypher.index("YIELD node AS dm, score") < cypher.index("WHERE")
        # Score columns only when search_text — present here
        assert "score_max" in cypher
        assert "score_median" in cypher
        assert params == {"search_text": "diel", "organism": "MED4", "value_kind": "numeric"}


class TestBuildGeneDerivedMetricsSummary:
    """Unit tests for build_gene_derived_metrics_summary (no Neo4j)."""

    def test_no_filters(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714", "PMM0001"])
        assert "UNWIND $locus_tags AS lt" in cypher
        assert "OPTIONAL MATCH (g:Gene {locus_tag: lt})" in cypher
        assert ("Derived_metric_quantifies_gene\n"
                "                    |Derived_metric_flags_gene\n"
                "                    |Derived_metric_classifies_gene") in cypher
        assert "WHERE dm IS NULL OR" not in cypher  # no DM filters
        assert params == {"locus_tags": ["PMM1714", "PMM0001"]}

    def test_metric_types_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], metric_types=["damping_ratio"])
        assert "WHERE dm IS NULL OR ( dm.metric_type IN $metric_types" in cypher
        assert params["metric_types"] == ["damping_ratio"]

    def test_value_kind_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], value_kind="numeric")
        assert "dm.value_kind = $value_kind" in cypher
        assert params["value_kind"] == "numeric"

    def test_compartment_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], compartment="vesicle")
        assert "dm.compartment = $compartment" in cypher
        assert params["compartment"] == "vesicle"

    def test_treatment_type_lowercased(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], treatment_type=["DIEL", "Darkness"])
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in cypher
        assert "toLower(t) IN $treatment_types_lower" in cypher
        assert params["treatment_types_lower"] == ["diel", "darkness"]

    def test_background_factors_lowercased(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], background_factors=["AXENIC"])
        assert "ANY(bf IN coalesce(dm.background_factors, [])" in cypher
        assert "toLower(bf) IN $bfs_lower" in cypher
        assert params["bfs_lower"] == ["axenic"]

    def test_publication_doi_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"],
            publication_doi=["10.1371/journal.pone.0043432"])
        assert "dm.publication_doi IN $publication_doi" in cypher
        assert params["publication_doi"] == ["10.1371/journal.pone.0043432"]

    def test_derived_metric_ids_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"],
            derived_metric_ids=["derived_metric:journal.pone.0043432:..."])
        assert "dm.id IN $derived_metric_ids" in cypher

    def test_combined_filters_anded(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"],
            value_kind="numeric", compartment="vesicle")
        # Both conditions inside the same `dm IS NULL OR (... AND ...)` group
        assert ("dm.value_kind = $value_kind AND dm.compartment = "
                "$compartment") in cypher

    def test_optional_match_cascade(self):
        cypher, _ = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], value_kind="numeric")
        # Cascade emits g IS NULL → not_found, dm IS NULL → not_matched
        assert ("collect(DISTINCT CASE WHEN g IS NULL THEN lt END)"
                " AS nf_raw") in cypher
        assert ("collect(DISTINCT CASE WHEN g IS NOT NULL AND dm IS NULL"
                " THEN lt END) AS nm_raw") in cypher

    def test_rows_map_includes_name(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        # Required for by_metric self-describing entries
        assert "name: dm.name" in cypher

    def test_returns_all_envelope_keys(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        for key in [
            "total_matching", "total_derived_metrics",
            "genes_with_metrics", "genes_without_metrics",
            "not_found", "not_matched",
            "by_value_kind", "by_metric_type",
            "by_metric", "by_compartment",
            "by_treatment_type", "by_background_factors", "by_publication",
        ]:
            assert key in cypher, f"missing envelope key: {key}"

    def test_by_metric_self_describing_shape(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        # by_metric carries derived_metric_id, name, metric_type, value_kind, count
        assert "[dm_id IN apoc.coll.toSet([r IN rows | r.dm_id])" in cypher
        assert "derived_metric_id: dm_id" in cypher
        assert "name: head([r IN rows WHERE r.dm_id = dm_id | r.name])" in cypher
        assert "value_kind: head([r IN rows WHERE r.dm_id = dm_id | r.vk])" in cypher

    def test_total_derived_metrics_distinct(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        assert ("size(apoc.coll.toSet([r IN rows | r.dm_id]))"
                " AS total_derived_metrics") in cypher

    def test_genes_without_metrics_arithmetic(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        assert ("size(input_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))"
                "\n         - size(not_found) AS genes_without_metrics") in cypher

    def test_locus_tags_param(self):
        _, params = build_gene_derived_metrics_summary(
            locus_tags=["A", "B"])
        assert params["locus_tags"] == ["A", "B"]


class TestBuildGeneDerivedMetrics:
    """Unit tests for build_gene_derived_metrics (detail)."""

    def test_no_filters(self):
        cypher, params = build_gene_derived_metrics(locus_tags=["PMM1714"])
        assert "UNWIND $locus_tags AS lt" in cypher
        assert "MATCH (g:Gene {locus_tag: lt})" in cypher
        assert ("MATCH (dm:DerivedMetric)-"
                "[r:Derived_metric_quantifies_gene\n"
                "                          |Derived_metric_flags_gene\n"
                "                          |Derived_metric_classifies_gene]"
                "->(g)") in cypher
        assert "WHERE" not in cypher.split("RETURN")[0]  # no filters
        assert params == {"locus_tags": ["PMM1714"]}

    def test_value_is_direct_r_access(self):
        # Post-rebuild: r.value, no CASE-on-value_kind, no properties(r)
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        assert "r.value AS value" in cypher
        assert "CASE dm.value_kind" not in cypher
        assert "properties(r)" not in cypher

    def test_returns_compact_columns(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        # 11 compact RETURN columns (13 Pydantic minus deferred adjusted_p_value, significant)
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "dm.id AS derived_metric_id",
            "dm.value_kind AS value_kind",
            "dm.name AS name",
            "r.value AS value",
            "dm.rankable = 'true' AS rankable",
            "dm.has_p_value = 'true' AS has_p_value",
        ]:
            assert col in cypher, f"missing compact column: {col}"

    def test_rankable_case_gates(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        for col in ["rank_by_metric", "metric_percentile", "metric_bucket"]:
            assert (f"CASE WHEN dm.rankable = 'true' THEN r.{col} "
                    f"ELSE null END AS {col}") in cypher

    def test_has_p_value_columns_deferred(self):
        # adjusted_p_value, significant: declared in Pydantic; absent from Cypher
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        assert "AS adjusted_p_value" not in cypher
        assert "AS significant" not in cypher

    def test_p_value_deferred_in_verbose(self):
        # Same forward-compat treatment; verbose RETURN omits r.p_value today
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"], verbose=True)
        assert "r.p_value" not in cypher

    def test_metric_types_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], metric_types=["damping_ratio"])
        assert "WHERE dm.metric_type IN $metric_types" in cypher
        assert params["metric_types"] == ["damping_ratio"]

    def test_value_kind_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], value_kind="numeric")
        assert "dm.value_kind = $value_kind" in cypher

    def test_compartment_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], compartment="vesicle")
        assert "dm.compartment = $compartment" in cypher

    def test_treatment_type_lowercased(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], treatment_type=["DIEL"])
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in cypher
        assert params["treatment_types_lower"] == ["diel"]

    def test_background_factors_lowercased(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], background_factors=["Axenic"])
        assert params["bfs_lower"] == ["axenic"]

    def test_publication_doi_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], publication_doi=["10.X/Y"])
        assert "dm.publication_doi IN $publication_doi" in cypher

    def test_derived_metric_ids_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], derived_metric_ids=["a"])
        assert "dm.id IN $derived_metric_ids" in cypher

    def test_combined_filters_anded(self):
        cypher, _ = build_gene_derived_metrics(
            locus_tags=["X"], value_kind="numeric", compartment="vesicle")
        assert ("WHERE dm.value_kind = $value_kind AND "
                "dm.compartment = $compartment") in cypher

    def test_verbose_adds_columns(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"], verbose=True)
        for col in [
            "dm.metric_type AS metric_type",
            "dm.field_description AS field_description",
            "dm.unit AS unit",
            "dm.compartment AS compartment",
            "coalesce(dm.treatment_type, []) AS treatment_type",
            "coalesce(dm.background_factors, []) AS background_factors",
            "dm.publication_doi AS publication_doi",
            "dm.treatment AS treatment",
            "dm.light_condition AS light_condition",
            "dm.experimental_context AS experimental_context",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_allowed_categories_case_gated_in_verbose(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"], verbose=True)
        assert ("CASE WHEN dm.value_kind = 'categorical'\n"
                "            THEN dm.allowed_categories ELSE null END "
                "AS allowed_categories") in cypher

    def test_compact_omits_verbose_fields(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"], verbose=False)
        for col in ["AS metric_type", "AS field_description", "AS unit",
                    "AS allowed_categories", "AS compartment",
                    "AS treatment_type", "AS background_factors",
                    "AS publication_doi", "AS treatment",
                    "AS light_condition", "AS experimental_context"]:
            assert col not in cypher, f"{col} should be verbose-only"

    def test_order_by(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        assert ("ORDER BY g.locus_tag ASC, dm.value_kind ASC, "
                "dm.id ASC") in cypher

    def test_limit_offset(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_no_skip_when_offset_zero(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], limit=10)
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_no_limit_when_none(self):
        cypher, params = build_gene_derived_metrics(locus_tags=["X"])
        assert "LIMIT" not in cypher
        assert "limit" not in params


class TestBuildListDerivedMetrics:
    """Tests for build_list_derived_metrics (detail)."""

    def test_no_filters_compact_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics()
        # Compact RETURN — all 18 columns present with aliases
        assert "dm.id AS derived_metric_id" in cypher
        assert "dm.name AS name" in cypher
        assert "dm.metric_type AS metric_type" in cypher
        assert "dm.value_kind AS value_kind" in cypher
        assert "dm.rankable = 'true' AS rankable" in cypher
        assert "dm.has_p_value = 'true' AS has_p_value" in cypher
        assert "dm.unit AS unit" in cypher
        assert "CASE WHEN dm.value_kind = 'categorical'" in cypher
        assert "THEN dm.allowed_categories ELSE null END AS allowed_categories" in cypher
        assert "dm.field_description AS field_description" in cypher
        assert "dm.organism_name AS organism_name" in cypher
        assert "dm.experiment_id AS experiment_id" in cypher
        assert "dm.publication_doi AS publication_doi" in cypher
        assert "dm.compartment AS compartment" in cypher
        assert "dm.omics_type AS omics_type" in cypher
        assert "coalesce(dm.treatment_type, []) AS treatment_type" in cypher
        assert "coalesce(dm.background_factors, []) AS background_factors" in cypher
        assert "dm.total_gene_count AS total_gene_count" in cypher
        assert "coalesce(dm.growth_phases, []) AS growth_phases" in cypher
        # p_value_threshold is intentionally absent (property doesn't exist)
        assert "p_value_threshold" not in cypher
        assert params == {}

    def test_order_by_default(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, _ = build_list_derived_metrics()
        assert (
            "ORDER BY dm.organism_name ASC, dm.value_kind ASC, dm.id ASC"
            in cypher
        )

    def test_search_text_adds_score_and_sort(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics(search_text="diel")
        assert (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)"
            in cypher
        )
        assert "       score" in cypher
        assert (
            "ORDER BY score DESC, dm.organism_name ASC, dm.value_kind ASC, dm.id ASC"
            in cypher
        )
        assert params == {"search_text": "diel"}

    def test_verbose_adds_three_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, _ = build_list_derived_metrics(verbose=True)
        assert "dm.treatment AS treatment" in cypher
        assert "dm.light_condition AS light_condition" in cypher
        assert "dm.experimental_context AS experimental_context" in cypher
        # p_value_threshold still NOT in Cypher — see spec §Verbose adds
        assert "p_value_threshold" not in cypher

    def test_verbose_false_omits_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, _ = build_list_derived_metrics(verbose=False)
        assert "dm.treatment AS treatment" not in cypher
        assert "dm.light_condition" not in cypher
        assert "dm.experimental_context" not in cypher

    def test_limit_and_offset(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics(limit=5, offset=10)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params == {"limit": 5, "offset": 10}

    def test_limit_none_omits_clause(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics(limit=None, offset=0)
        assert "LIMIT" not in cypher
        assert "SKIP" not in cypher
        assert params == {}

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics(
            organism="NATL2A", value_kind="boolean", rankable=False, limit=10)
        assert "WHERE" in cypher
        assert "dm.value_kind = $value_kind" in cypher
        assert "dm.rankable = $rankable_str" in cypher
        assert params == {
            "organism": "NATL2A",
            "value_kind": "boolean",
            "rankable_str": "false",
            "limit": 10,
        }

    def test_allowed_categories_case_gated(self):
        """Defensive CASE-gating: allowed_categories null unless value_kind='categorical'."""
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, _ = build_list_derived_metrics()
        # Must use CASE, not raw dm.allowed_categories
        assert "dm.allowed_categories AS allowed_categories" not in cypher
        assert (
            "CASE WHEN dm.value_kind = 'categorical'"
            "\n            THEN dm.allowed_categories ELSE null END AS allowed_categories"
            in cypher
        )


class TestBuildGenesByNumericMetricDiagnostics:
    """Unit tests for build_genes_by_numeric_metric_diagnostics (no Neo4j)."""

    def test_metric_types_filter(self):
        cypher, params = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"])
        assert "dm.metric_type IN $metric_types" in cypher
        assert params["metric_types"] == ["damping_ratio"]

    def test_derived_metric_ids_filter(self):
        cypher, params = build_genes_by_numeric_metric_diagnostics(
            derived_metric_ids=["dm:abc"])
        assert "dm.id IN $derived_metric_ids" in cypher
        assert params["derived_metric_ids"] == ["dm:abc"]

    def test_value_kind_hardcoded(self):
        # Builder always emits the value_kind='numeric' guard
        cypher, params = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"])
        assert "dm.value_kind = $value_kind" in cypher
        assert params["value_kind"] == "numeric"

    def test_value_kind_hardcoded_with_no_other_filters(self):
        # Even minimal call (no selection) carries the hardcoded guard
        cypher, params = build_genes_by_numeric_metric_diagnostics()
        assert "dm.value_kind = $value_kind" in cypher
        assert params["value_kind"] == "numeric"

    def test_returns_canonical_columns(self):
        cypher, _ = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"])
        for col in [
            "dm.id AS derived_metric_id",
            "dm.metric_type AS metric_type",
            "dm.value_kind AS value_kind",
            "dm.name AS name",
            "dm.rankable = 'true' AS rankable",
            "dm.has_p_value = 'true' AS has_p_value",
            "dm.total_gene_count AS total_gene_count",
            "dm.organism_name AS organism_name",
        ]:
            assert col in cypher, f"missing canonical column: {col}"

    def test_organism_filter(self):
        cypher, params = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"], organism="MED4")
        assert ("ALL(word IN split(toLower($organism), ' ')"
                " WHERE toLower(dm.organism_name) CONTAINS word)") in cypher
        assert params["organism"] == "MED4"

    def test_compartment_filter(self):
        cypher, params = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"], compartment="vesicle")
        assert "dm.compartment = $compartment" in cypher
        assert params["compartment"] == "vesicle"

    def test_treatment_type_lower(self):
        cypher, params = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"], treatment_type=["DIEL"])
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in cypher
        assert "toLower(t) IN $treatment_types_lower" in cypher
        assert params["treatment_types_lower"] == ["diel"]

    def test_background_factors_lower(self):
        cypher, params = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"], background_factors=["AXENIC"])
        assert "ANY(bf IN coalesce(dm.background_factors, [])" in cypher
        assert "toLower(bf) IN $background_factors_lower" in cypher
        assert params["background_factors_lower"] == ["axenic"]

    def test_combined_filters(self):
        cypher, _ = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"], organism="MED4",
            compartment="vesicle")
        # Conditions AND-joined
        assert " AND " in cypher.split("RETURN")[0]
        assert "dm.metric_type IN $metric_types" in cypher
        assert "dm.value_kind = $value_kind" in cypher
        assert "dm.compartment = $compartment" in cypher

    def test_order_by(self):
        cypher, _ = build_genes_by_numeric_metric_diagnostics(
            metric_types=["damping_ratio"])
        assert "ORDER BY dm.id ASC" in cypher


class TestBuildGenesByNumericMetricSummary:
    """Unit tests for build_genes_by_numeric_metric_summary (no Neo4j)."""

    def test_minimal_call(self):
        cypher, params = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"])
        assert ("MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->"
                "(g:Gene)") in cypher
        assert "WHERE dm.id IN $derived_metric_ids" in cypher
        assert params == {"derived_metric_ids": ["dm:abc"]}

    def test_locus_tags_filter(self):
        cypher, params = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"], locus_tags=["PMM1545"])
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == ["PMM1545"]

    def test_min_max_value(self):
        cypher, params = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"], min_value=1.5, max_value=10.0)
        assert "r.value >= $min_value" in cypher
        assert "r.value <= $max_value" in cypher
        assert params["min_value"] == 1.5
        assert params["max_value"] == 10.0

    def test_min_max_percentile(self):
        cypher, params = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"],
            min_percentile=90.0, max_percentile=99.0)
        assert "r.metric_percentile >= $min_percentile" in cypher
        assert "r.metric_percentile <= $max_percentile" in cypher
        assert params["min_percentile"] == 90.0
        assert params["max_percentile"] == 99.0

    def test_bucket_filter(self):
        cypher, params = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"], bucket=["top_decile"])
        assert "r.metric_bucket IN $bucket" in cypher
        assert params["bucket"] == ["top_decile"]

    def test_max_rank(self):
        cypher, params = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"], max_rank=5)
        assert "r.rank_by_metric <= $max_rank" in cypher
        assert params["max_rank"] == 5

    def test_combined_edge_filters(self):
        cypher, _ = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"],
            min_value=1.0, bucket=["top_decile"], max_rank=10)
        # All clauses AND-joined in a single WHERE
        where_block = cypher.split("RETURN")[0]
        assert "dm.id IN $derived_metric_ids" in where_block
        assert "r.value >= $min_value" in where_block
        assert "r.metric_bucket IN $bucket" in where_block
        assert "r.rank_by_metric <= $max_rank" in where_block
        assert " AND " in where_block

    def test_returns_expected_envelope_columns(self):
        cypher, _ = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"])
        for col in [
            "AS total_matching",
            "AS total_derived_metrics",
            "AS total_genes",
            "AS by_organism",
            "AS by_compartment",
            "AS by_publication",
            "AS by_experiment",
            "AS by_metric",
            "AS top_categories_raw",
            "AS genes_per_metric_max",
            "AS genes_per_metric_median",
        ]:
            assert col in cypher, f"missing envelope column: {col}"

    def test_by_metric_shape(self):
        cypher, _ = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"])
        # Each by_metric entry has these 17 keys
        for key in [
            "derived_metric_id: dm_id",
            "name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name])",
            "metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt])",
            "value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk])",
            "count:       size([x IN rows WHERE x.dm_id = dm_id])",
            "value_min:",
            "value_max:",
            "value_median:",
            "value_q1:",
            "value_q3:",
            "dm_value_min:",
            "dm_value_q1:",
            "dm_value_median:",
            "dm_value_q3:",
            "dm_value_max:",
            "rank_min:",
            "rank_max:",
        ]:
            assert key in cypher, f"missing by_metric key: {key}"

    def test_dm_value_props_in_return(self):
        # All 5 precomputed DM-distribution props read in WITH/collect
        cypher, _ = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"])
        for prop in ["dm.value_min", "dm.value_q1", "dm.value_median",
                     "dm.value_q3", "dm.value_max"]:
            assert prop in cypher, f"missing precomputed DM prop: {prop}"

    def test_value_median_via_sorted_index(self):
        cypher, _ = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"])
        # Median computed via sort + size/2 index, not percentileCont
        assert "apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])" in cypher
        assert "percentileCont" not in cypher

    def test_rank_min_max_filter_nulls(self):
        cypher, _ = build_genes_by_numeric_metric_summary(
            derived_metric_ids=["dm:abc"])
        # Rank list comprehension filters non-null ranks
        assert ("[x IN rows WHERE x.dm_id = dm_id AND x.rank IS NOT NULL"
                " | x.rank]") in cypher


class TestBuildGenesByNumericMetric:
    """Unit tests for build_genes_by_numeric_metric (detail)."""

    def test_minimal_call(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"])
        assert ("MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->"
                "(g:Gene)") in cypher
        assert "WHERE dm.id IN $derived_metric_ids" in cypher
        assert params == {"derived_metric_ids": ["dm:abc"]}

    def test_returns_expected_compact_columns(self):
        # Exactly 14 compact RETURN columns
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"])
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "g.product AS product",
            "g.gene_category AS gene_category",
            "g.organism_name AS organism_name",
            "dm.id AS derived_metric_id",
            "dm.name AS name",
            "dm.value_kind AS value_kind",
            "dm.rankable = 'true' AS rankable",
            "dm.has_p_value = 'true' AS has_p_value",
            "r.value AS value",
            "AS rank_by_metric",
            "AS metric_percentile",
            "AS metric_bucket",
        ]:
            assert col in cypher, f"missing compact column: {col}"

    def test_compact_omits_verbose_moved_fields(self):
        # 6 fields verbose-moved; 2 forward-compat absent
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], verbose=False)
        for col in [
            "AS metric_type",
            "AS compartment",
            "AS experiment_id",
            "AS publication_doi",
            "AS treatment_type",
            "AS background_factors",
        ]:
            assert col not in cypher, f"{col} should be verbose-only"
        # Forward-compat (Pydantic-only)
        assert "AS adjusted_p_value" not in cypher
        assert "AS significant" not in cypher

    def test_value_is_direct_r_access(self):
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"])
        assert "r.value AS value" in cypher
        assert "CASE dm.value_kind" not in cypher
        assert "properties(r)" not in cypher

    def test_rankable_case_gates(self):
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"])
        for col in ["rank_by_metric", "metric_percentile", "metric_bucket"]:
            assert (f"CASE WHEN dm.rankable = 'true' THEN r.{col}"
                    f" ELSE null END AS {col}") in cypher

    def test_has_p_value_columns_deferred(self):
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"])
        assert "AS adjusted_p_value" not in cypher
        assert "AS significant" not in cypher

    def test_p_value_deferred_in_verbose(self):
        # verbose RETURN does NOT contain r.p_value today
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], verbose=True)
        assert "r.p_value" not in cypher

    def test_rankable_has_p_value_coerced(self):
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"])
        assert "dm.rankable = 'true' AS rankable" in cypher
        assert "dm.has_p_value = 'true' AS has_p_value" in cypher

    def test_locus_tags_filter(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], locus_tags=["PMM1545"])
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == ["PMM1545"]

    def test_min_max_value(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], min_value=1.5, max_value=10.0)
        assert "r.value >= $min_value" in cypher
        assert "r.value <= $max_value" in cypher
        assert params["min_value"] == 1.5
        assert params["max_value"] == 10.0

    def test_min_max_percentile(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"],
            min_percentile=90.0, max_percentile=99.0)
        assert "r.metric_percentile >= $min_percentile" in cypher
        assert "r.metric_percentile <= $max_percentile" in cypher

    def test_bucket_filter(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], bucket=["top_decile"])
        assert "r.metric_bucket IN $bucket" in cypher
        assert params["bucket"] == ["top_decile"]

    def test_max_rank_filter(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], max_rank=5)
        assert "r.rank_by_metric <= $max_rank" in cypher
        assert params["max_rank"] == 5

    def test_verbose_adds_columns(self):
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], verbose=True)
        for col in [
            "dm.metric_type AS metric_type",
            "dm.field_description AS field_description",
            "dm.unit AS unit",
            "dm.compartment AS compartment",
            "dm.experiment_id AS experiment_id",
            "dm.publication_doi AS publication_doi",
            "coalesce(dm.treatment_type, []) AS treatment_type",
            "coalesce(dm.background_factors, []) AS background_factors",
            "dm.treatment AS treatment",
            "dm.light_condition AS light_condition",
            "dm.experimental_context AS experimental_context",
            "g.function_description AS gene_function_description",
            "g.gene_summary AS gene_summary",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_order_by(self):
        cypher, _ = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"])
        assert ("ORDER BY r.rank_by_metric ASC, r.value DESC, "
                "dm.id ASC, g.locus_tag ASC") in cypher

    def test_limit_offset(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_no_skip_when_offset_zero(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"], limit=10)
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_no_limit_when_none(self):
        cypher, params = build_genes_by_numeric_metric(
            derived_metric_ids=["dm:abc"])
        assert "LIMIT" not in cypher
        assert "limit" not in params


class TestBuildGenesByBooleanMetricDiagnostics:
    """Unit tests for build_genes_by_boolean_metric_diagnostics (no Neo4j)."""

    def test_no_filters(self):
        # Even minimal call (no selection) carries the hardcoded value_kind guard
        cypher, params = build_genes_by_boolean_metric_diagnostics()
        assert "MATCH (dm:DerivedMetric)" in cypher
        assert "dm.value_kind = $value_kind" in cypher
        assert params == {"value_kind": "boolean"}

    def test_metric_types_filter(self):
        cypher, params = build_genes_by_boolean_metric_diagnostics(
            metric_types=["vesicle_proteome_member"])
        assert "dm.metric_type IN $metric_types" in cypher
        assert params["metric_types"] == ["vesicle_proteome_member"]

    def test_derived_metric_ids_filter(self):
        cypher, params = build_genes_by_boolean_metric_diagnostics(
            derived_metric_ids=["dm:abc"])
        assert "dm.id IN $derived_metric_ids" in cypher
        assert params["derived_metric_ids"] == ["dm:abc"]

    def test_organism_filter(self):
        cypher, params = build_genes_by_boolean_metric_diagnostics(
            metric_types=["vesicle_proteome_member"], organism="MED4")
        assert ("ALL(word IN split(toLower($organism), ' ')"
                " WHERE toLower(dm.organism_name) CONTAINS word)") in cypher
        assert params["organism"] == "MED4"

    def test_scoping_filters_combine(self):
        cypher, params = build_genes_by_boolean_metric_diagnostics(
            metric_types=["vesicle_proteome_member"],
            compartment="vesicle",
            treatment_type=["DIEL"],
            background_factors=["AXENIC"],
            growth_phases=["EXPONENTIAL"],
            publication_doi=["10.1/foo"],
            experiment_ids=["exp:1"],
        )
        where_block = cypher.split("RETURN")[0]
        assert "dm.metric_type IN $metric_types" in where_block
        assert "dm.compartment = $compartment" in where_block
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in where_block
        assert "ANY(bf IN coalesce(dm.background_factors, [])" in where_block
        assert "ANY(gp IN coalesce(dm.growth_phases, [])" in where_block
        assert "dm.publication_doi IN $publication_doi" in where_block
        assert "dm.experiment_id IN $experiment_ids" in where_block
        assert " AND " in where_block
        assert params["compartment"] == "vesicle"
        assert params["treatment_types_lower"] == ["diel"]
        assert params["background_factors_lower"] == ["axenic"]
        assert params["growth_phases_lower"] == ["exponential"]
        assert params["publication_doi"] == ["10.1/foo"]
        assert params["experiment_ids"] == ["exp:1"]

    def test_value_kind_hardcoded_boolean(self):
        cypher, params = build_genes_by_boolean_metric_diagnostics(
            metric_types=["vesicle_proteome_member"])
        assert "dm.value_kind = $value_kind" in cypher
        assert params["value_kind"] == "boolean"

    def test_returns_expected_columns(self):
        cypher, _ = build_genes_by_boolean_metric_diagnostics(
            metric_types=["vesicle_proteome_member"])
        for col in [
            "dm.id AS derived_metric_id",
            "dm.metric_type AS metric_type",
            "dm.value_kind AS value_kind",
            "dm.name AS name",
            "dm.total_gene_count AS total_gene_count",
            "dm.organism_name AS organism_name",
        ]:
            assert col in cypher, f"missing canonical column: {col}"
        # Boolean diagnostics has NO rankable / has_p_value / allowed_categories
        assert "AS rankable" not in cypher
        assert "AS has_p_value" not in cypher
        assert "AS allowed_categories" not in cypher
        assert "ORDER BY dm.id ASC" in cypher


class TestBuildGenesByBooleanMetricSummary:
    """Unit tests for build_genes_by_boolean_metric_summary (no Neo4j)."""

    def test_no_filters(self):
        cypher, params = build_genes_by_boolean_metric_summary(
            derived_metric_ids=["dm:abc"])
        assert ("MATCH (dm:DerivedMetric)-[r:Derived_metric_flags_gene]->"
                "(g:Gene)") in cypher
        assert "WHERE dm.id IN $derived_metric_ids" in cypher
        assert params == {"derived_metric_ids": ["dm:abc"]}

    def test_locus_tags_filter(self):
        cypher, params = build_genes_by_boolean_metric_summary(
            derived_metric_ids=["dm:abc"], locus_tags=["PMM0090"])
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == ["PMM0090"]

    def test_flag_true_filter(self):
        cypher, params = build_genes_by_boolean_metric_summary(
            derived_metric_ids=["dm:abc"], flag=True)
        assert "r.value = $flag_str" in cypher
        assert params["flag_str"] == "true"

    def test_flag_false_filter(self):
        cypher, params = build_genes_by_boolean_metric_summary(
            derived_metric_ids=["dm:abc"], flag=False)
        assert "r.value = $flag_str" in cypher
        assert params["flag_str"] == "false"

    def test_returns_expected_columns(self):
        cypher, _ = build_genes_by_boolean_metric_summary(
            derived_metric_ids=["dm:abc"])
        for col in [
            "AS total_matching",
            "AS total_derived_metrics",
            "AS total_genes",
            "AS by_organism",
            "AS by_compartment",
            "AS by_publication",
            "AS by_experiment",
            "AS by_value",
            "AS top_categories_raw",
            "AS by_metric",
            "AS genes_per_metric_max",
            "AS genes_per_metric_median",
        ]:
            assert col in cypher, f"missing envelope column: {col}"

    def test_by_metric_carries_dm_precomputed_stats(self):
        cypher, _ = build_genes_by_boolean_metric_summary(
            derived_metric_ids=["dm:abc"])
        # Per-DM filtered counts
        for key in [
            "derived_metric_id: dm_id",
            "name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name])",
            "metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt])",
            "value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk])",
            "count:       size([x IN rows WHERE x.dm_id = dm_id])",
            "true_count:  size([x IN rows WHERE x.dm_id = dm_id AND x.value = 'true'])",
            "false_count: size([x IN rows WHERE x.dm_id = dm_id AND x.value = 'false'])",
            "dm_total_gene_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_total])",
            "dm_true_count:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_true])",
            "dm_false_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_false])",
        ]:
            assert key in cypher, f"missing by_metric key: {key}"
        # Precomputed DM-distribution props read in WITH/collect
        for prop in ["dm.total_gene_count", "dm.flag_true_count",
                     "dm.flag_false_count"]:
            assert prop in cypher, f"missing precomputed DM prop: {prop}"


class TestBuildGenesByBooleanMetric:
    """Unit tests for build_genes_by_boolean_metric (detail)."""

    def test_no_filters(self):
        cypher, params = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"])
        assert ("MATCH (dm:DerivedMetric)-[r:Derived_metric_flags_gene]->"
                "(g:Gene)") in cypher
        assert "WHERE dm.id IN $derived_metric_ids" in cypher
        assert params == {"derived_metric_ids": ["dm:abc"]}

    def test_locus_tags_filter(self):
        cypher, params = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"], locus_tags=["PMM0090"])
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == ["PMM0090"]

    def test_flag_filter(self):
        cypher, params = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"], flag=True)
        assert "r.value = $flag_str" in cypher
        assert params["flag_str"] == "true"
        cypher, params = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"], flag=False)
        assert params["flag_str"] == "false"

    def test_returns_expected_columns_compact(self):
        cypher, _ = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"])
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "g.product AS product",
            "g.gene_category AS gene_category",
            "g.organism_name AS organism_name",
            "dm.id AS derived_metric_id",
            "dm.name AS name",
            "dm.value_kind AS value_kind",
            "dm.rankable = 'true' AS rankable",
            "dm.has_p_value = 'true' AS has_p_value",
            "r.value AS value",
        ]:
            assert col in cypher, f"missing compact column: {col}"
        # Verbose columns are absent in compact mode
        for col in [
            "AS metric_type",
            "AS compartment",
            "AS experiment_id",
            "AS publication_doi",
            "AS treatment_type",
            "AS background_factors",
            "AS gene_function_description",
            "AS gene_summary",
        ]:
            assert col not in cypher, f"{col} should be verbose-only"

    def test_returns_expected_columns_verbose(self):
        cypher, _ = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"], verbose=True)
        for col in [
            "dm.metric_type AS metric_type",
            "dm.field_description AS field_description",
            "dm.unit AS unit",
            "dm.compartment AS compartment",
            "dm.experiment_id AS experiment_id",
            "dm.publication_doi AS publication_doi",
            "coalesce(dm.treatment_type, []) AS treatment_type",
            "coalesce(dm.background_factors, []) AS background_factors",
            "dm.treatment AS treatment",
            "dm.light_condition AS light_condition",
            "dm.experimental_context AS experimental_context",
            "g.function_description AS gene_function_description",
            "g.gene_summary AS gene_summary",
        ]:
            assert col in cypher, f"missing verbose column: {col}"
        # Categorical-only verbose addition is absent here
        assert "AS allowed_categories" not in cypher

    def test_order_by(self):
        cypher, _ = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"])
        assert "ORDER BY dm.id ASC, g.locus_tag ASC" in cypher

    def test_limit_clause(self):
        cypher, params = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"], limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_limit_none(self):
        cypher, params = build_genes_by_boolean_metric(
            derived_metric_ids=["dm:abc"])
        assert "LIMIT" not in cypher
        assert "SKIP" not in cypher
        assert "limit" not in params
        assert "offset" not in params


class TestBuildGenesByCategoricalMetricDiagnostics:
    """Unit tests for build_genes_by_categorical_metric_diagnostics (no Neo4j)."""

    def test_no_filters(self):
        cypher, params = build_genes_by_categorical_metric_diagnostics()
        assert "MATCH (dm:DerivedMetric)" in cypher
        assert "dm.value_kind = $value_kind" in cypher
        assert params == {"value_kind": "categorical"}

    def test_metric_types_filter(self):
        cypher, params = build_genes_by_categorical_metric_diagnostics(
            metric_types=["predicted_subcellular_localization"])
        assert "dm.metric_type IN $metric_types" in cypher
        assert params["metric_types"] == ["predicted_subcellular_localization"]

    def test_derived_metric_ids_filter(self):
        cypher, params = build_genes_by_categorical_metric_diagnostics(
            derived_metric_ids=["dm:abc"])
        assert "dm.id IN $derived_metric_ids" in cypher
        assert params["derived_metric_ids"] == ["dm:abc"]

    def test_organism_filter(self):
        cypher, params = build_genes_by_categorical_metric_diagnostics(
            metric_types=["predicted_subcellular_localization"],
            organism="MED4")
        assert ("ALL(word IN split(toLower($organism), ' ')"
                " WHERE toLower(dm.organism_name) CONTAINS word)") in cypher
        assert params["organism"] == "MED4"

    def test_scoping_filters_combine(self):
        cypher, params = build_genes_by_categorical_metric_diagnostics(
            metric_types=["predicted_subcellular_localization"],
            compartment="cell",
            treatment_type=["DIEL"],
            background_factors=["AXENIC"],
            growth_phases=["EXPONENTIAL"],
            publication_doi=["10.1/foo"],
            experiment_ids=["exp:1"],
        )
        where_block = cypher.split("RETURN")[0]
        assert "dm.metric_type IN $metric_types" in where_block
        assert "dm.compartment = $compartment" in where_block
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in where_block
        assert "ANY(bf IN coalesce(dm.background_factors, [])" in where_block
        assert "ANY(gp IN coalesce(dm.growth_phases, [])" in where_block
        assert "dm.publication_doi IN $publication_doi" in where_block
        assert "dm.experiment_id IN $experiment_ids" in where_block
        assert " AND " in where_block
        assert params["compartment"] == "cell"

    def test_value_kind_hardcoded_categorical(self):
        cypher, params = build_genes_by_categorical_metric_diagnostics(
            metric_types=["predicted_subcellular_localization"])
        assert "dm.value_kind = $value_kind" in cypher
        assert params["value_kind"] == "categorical"

    def test_returns_expected_columns(self):
        cypher, _ = build_genes_by_categorical_metric_diagnostics(
            metric_types=["predicted_subcellular_localization"])
        for col in [
            "dm.id AS derived_metric_id",
            "dm.metric_type AS metric_type",
            "dm.value_kind AS value_kind",
            "dm.name AS name",
            "dm.total_gene_count AS total_gene_count",
            "dm.organism_name AS organism_name",
            "dm.allowed_categories AS allowed_categories",
        ]:
            assert col in cypher, f"missing canonical column: {col}"
        # Categorical diagnostics has NO rankable / has_p_value
        assert "AS rankable" not in cypher
        assert "AS has_p_value" not in cypher
        assert "ORDER BY dm.id ASC" in cypher


class TestBuildGenesByCategoricalMetricSummary:
    """Unit tests for build_genes_by_categorical_metric_summary (no Neo4j)."""

    def test_no_filters(self):
        cypher, params = build_genes_by_categorical_metric_summary(
            derived_metric_ids=["dm:abc"])
        assert ("MATCH (dm:DerivedMetric)-[r:Derived_metric_classifies_gene]->"
                "(g:Gene)") in cypher
        assert "WHERE dm.id IN $derived_metric_ids" in cypher
        assert params == {"derived_metric_ids": ["dm:abc"]}

    def test_locus_tags_filter(self):
        cypher, params = build_genes_by_categorical_metric_summary(
            derived_metric_ids=["dm:abc"], locus_tags=["PMM0097"])
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == ["PMM0097"]

    def test_categories_filter(self):
        cypher, params = build_genes_by_categorical_metric_summary(
            derived_metric_ids=["dm:abc"],
            categories=["Outer Membrane", "Periplasmic"])
        assert "r.value IN $categories" in cypher
        assert params["categories"] == ["Outer Membrane", "Periplasmic"]

    def test_returns_expected_columns(self):
        cypher, _ = build_genes_by_categorical_metric_summary(
            derived_metric_ids=["dm:abc"])
        for col in [
            "AS total_matching",
            "AS total_derived_metrics",
            "AS total_genes",
            "AS by_organism",
            "AS by_compartment",
            "AS by_publication",
            "AS by_experiment",
            "AS by_category",
            "AS top_categories_raw",
            "AS by_metric",
            "AS genes_per_metric_max",
            "AS genes_per_metric_median",
        ]:
            assert col in cypher, f"missing envelope column: {col}"

    def test_by_metric_carries_dm_precomputed_histogram(self):
        cypher, _ = build_genes_by_categorical_metric_summary(
            derived_metric_ids=["dm:abc"])
        # Filtered slice histogram for the matching rows
        assert ("by_category: apoc.coll.frequencies("
                "[x IN rows WHERE x.dm_id = dm_id | x.value])") in cypher
        # Full-DM precomputed histogram via zipped category_labels / category_counts
        assert "dm_by_category:" in cypher
        assert ("[i IN range(0,\n"
                "            size(head([x IN rows WHERE x.dm_id = dm_id "
                "| x.dm_labels])) - 1)") in cypher
        assert ("{item:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_labels])[i],"
                "\n           count: head([x IN rows WHERE x.dm_id = dm_id "
                "| x.dm_counts])[i]}") in cypher
        # WITH/collect reads the precomputed DM props
        for prop in ["dm.total_gene_count", "dm.category_labels",
                     "dm.category_counts", "dm.allowed_categories"]:
            assert prop in cypher, f"missing precomputed DM prop: {prop}"

    def test_by_metric_includes_allowed_categories(self):
        cypher, _ = build_genes_by_categorical_metric_summary(
            derived_metric_ids=["dm:abc"])
        # Per-DM dict carries allowed_categories (passed through from collect)
        assert ("allowed_categories:  head([x IN rows WHERE x.dm_id = dm_id "
                "| x.dm_allowed])") in cypher
        # And dm_total_gene_count
        assert ("dm_total_gene_count: head([x IN rows WHERE x.dm_id = dm_id "
                "| x.dm_total])") in cypher


class TestBuildGenesByCategoricalMetric:
    """Unit tests for build_genes_by_categorical_metric (detail)."""

    def test_no_filters(self):
        cypher, params = build_genes_by_categorical_metric(
            derived_metric_ids=["dm:abc"])
        assert ("MATCH (dm:DerivedMetric)-[r:Derived_metric_classifies_gene]->"
                "(g:Gene)") in cypher
        assert "WHERE dm.id IN $derived_metric_ids" in cypher
        assert params == {"derived_metric_ids": ["dm:abc"]}

    def test_locus_tags_filter(self):
        cypher, params = build_genes_by_categorical_metric(
            derived_metric_ids=["dm:abc"], locus_tags=["PMM0097"])
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == ["PMM0097"]

    def test_categories_filter(self):
        cypher, params = build_genes_by_categorical_metric(
            derived_metric_ids=["dm:abc"],
            categories=["Outer Membrane", "Periplasmic"])
        assert "r.value IN $categories" in cypher
        assert params["categories"] == ["Outer Membrane", "Periplasmic"]

    def test_returns_expected_columns_compact(self):
        cypher, _ = build_genes_by_categorical_metric(
            derived_metric_ids=["dm:abc"])
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "g.product AS product",
            "g.gene_category AS gene_category",
            "g.organism_name AS organism_name",
            "dm.id AS derived_metric_id",
            "dm.name AS name",
            "dm.value_kind AS value_kind",
            "dm.rankable = 'true' AS rankable",
            "dm.has_p_value = 'true' AS has_p_value",
            "r.value AS value",
        ]:
            assert col in cypher, f"missing compact column: {col}"
        # Verbose columns are absent in compact mode
        for col in [
            "AS metric_type",
            "AS compartment",
            "AS experiment_id",
            "AS publication_doi",
            "AS treatment_type",
            "AS background_factors",
            "AS gene_function_description",
            "AS gene_summary",
            "AS allowed_categories",
        ]:
            assert col not in cypher, f"{col} should be verbose-only"

    def test_returns_expected_columns_verbose(self):
        cypher, _ = build_genes_by_categorical_metric(
            derived_metric_ids=["dm:abc"], verbose=True)
        for col in [
            "dm.metric_type AS metric_type",
            "dm.field_description AS field_description",
            "dm.unit AS unit",
            "dm.compartment AS compartment",
            "dm.experiment_id AS experiment_id",
            "dm.publication_doi AS publication_doi",
            "coalesce(dm.treatment_type, []) AS treatment_type",
            "coalesce(dm.background_factors, []) AS background_factors",
            "dm.treatment AS treatment",
            "dm.light_condition AS light_condition",
            "dm.experimental_context AS experimental_context",
            "g.function_description AS gene_function_description",
            "g.gene_summary AS gene_summary",
            "dm.allowed_categories AS allowed_categories",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_order_by(self):
        cypher, _ = build_genes_by_categorical_metric(
            derived_metric_ids=["dm:abc"])
        assert "ORDER BY r.value ASC, dm.id ASC, g.locus_tag ASC" in cypher

    def test_limit_clause(self):
        cypher, params = build_genes_by_categorical_metric(
            derived_metric_ids=["dm:abc"], limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_limit_none(self):
        cypher, params = build_genes_by_categorical_metric(
            derived_metric_ids=["dm:abc"])
        assert "LIMIT" not in cypher
        assert "SKIP" not in cypher
        assert "limit" not in params
        assert "offset" not in params


# ---------------------------------------------------------------------------
# list_metabolites — Phase 1 (Stage 1 RED)
# ---------------------------------------------------------------------------


class TestBuildListMetabolites:
    """Detail-builder tests for list_metabolites.

    Imports happen inside each test so pre-impl test collection still passes.
    """

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import build_list_metabolites
        return build_list_metabolites(**kwargs)

    def test_no_filters(self):
        """No filters: MATCH (m:Metabolite) with no WHERE / no fulltext."""
        cypher, params = self._build()
        assert "MATCH (m:Metabolite)" in cypher
        assert "WHERE" not in cypher
        assert "fulltext" not in cypher
        assert "score" not in cypher
        assert params == {}

    def test_metabolite_ids_filter(self):
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00031", "kegg.compound:C00002"])
        assert "m.id IN $metabolite_ids" in cypher
        assert params["metabolite_ids"] == [
            "kegg.compound:C00031", "kegg.compound:C00002"]

    def test_kegg_compound_ids_filter(self):
        cypher, params = self._build(kegg_compound_ids=["C00031"])
        assert "m.kegg_compound_id IN $kegg_compound_ids" in cypher
        assert params["kegg_compound_ids"] == ["C00031"]

    def test_chebi_ids_filter(self):
        cypher, params = self._build(chebi_ids=["4167", "15422"])
        assert "m.chebi_id IN $chebi_ids" in cypher
        assert params["chebi_ids"] == ["4167", "15422"]

    def test_hmdb_ids_filter(self):
        cypher, params = self._build(hmdb_ids=["HMDB0000122"])
        assert "m.hmdb_id IN $hmdb_ids" in cypher
        assert params["hmdb_ids"] == ["HMDB0000122"]

    def test_mnxm_ids_filter(self):
        cypher, params = self._build(mnxm_ids=["MNXM1364061"])
        assert "m.mnxm_id IN $mnxm_ids" in cypher
        assert params["mnxm_ids"] == ["MNXM1364061"]

    def test_elements_filter_single(self):
        """elements filter uses ALL(... IN coalesce(m.elements, []))."""
        cypher, params = self._build(elements=["N"])
        assert (
            "ALL(e IN $elements WHERE e IN coalesce(m.elements, []))"
            in cypher
        )
        assert params["elements"] == ["N"]

    def test_elements_filter_multi(self):
        """Two-element AND-of-presence — single ALL(...) clause covers both."""
        cypher, params = self._build(elements=["N", "P"])
        assert (
            "ALL(e IN $elements WHERE e IN coalesce(m.elements, []))"
            in cypher
        )
        assert params["elements"] == ["N", "P"]

    def test_mass_min_filter(self):
        cypher, params = self._build(mass_min=60.0)
        assert "m.mass >= $mass_min" in cypher
        assert params["mass_min"] == 60.0

    def test_mass_max_filter(self):
        cypher, params = self._build(mass_max=1000.0)
        assert "m.mass <= $mass_max" in cypher
        assert params["mass_max"] == 1000.0

    def test_mass_range_combined(self):
        cypher, params = self._build(mass_min=60.0, mass_max=1000.0)
        assert "m.mass >= $mass_min" in cypher
        assert "m.mass <= $mass_max" in cypher
        assert params["mass_min"] == 60.0
        assert params["mass_max"] == 1000.0

    def test_organism_names_filter(self):
        """organism_names_lc filter uses ANY(... toLower(o) IN $organism_names_lc)."""
        cypher, params = self._build(
            organism_names_lc=["prochlorococcus med4"])
        assert (
            "ANY(o IN coalesce(m.organism_names, []) "
            "WHERE toLower(o) IN $organism_names_lc)"
            in cypher
        )
        assert params["organism_names_lc"] == ["prochlorococcus med4"]

    def test_pathway_ids_filter(self):
        """pathway_ids filter uses ANY against m.pathway_ids."""
        cypher, params = self._build(
            pathway_ids=["kegg.pathway:ko00910"])
        assert (
            "ANY(p IN coalesce(m.pathway_ids, []) WHERE p IN $pathway_ids)"
            in cypher
        )
        assert params["pathway_ids"] == ["kegg.pathway:ko00910"]

    def test_evidence_sources_filter(self):
        """evidence_sources filter uses ANY against m.evidence_sources."""
        cypher, params = self._build(evidence_sources=["transport"])
        assert (
            "ANY(s IN $evidence_sources "
            "WHERE s IN coalesce(m.evidence_sources, []))"
            in cypher
        )
        assert params["evidence_sources"] == ["transport"]

    def test_combined_filters(self):
        """Multiple filters AND-joined in one WHERE block."""
        cypher, params = self._build(
            elements=["N"],
            organism_names_lc=["prochlorococcus med4"],
            mass_min=60.0,
        )
        assert "WHERE" in cypher
        assert " AND " in cypher
        assert params["elements"] == ["N"]
        assert params["organism_names_lc"] == ["prochlorococcus med4"]
        assert params["mass_min"] == 60.0

    def test_search_uses_fulltext_entrypoint(self):
        """Search variant uses the metaboliteFullText index."""
        cypher, params = self._build(search_text="glucose")
        assert "metaboliteFullText" in cypher
        assert "YIELD node AS m, score" in cypher
        assert params["search"] == "glucose"

    def test_returns_compact_columns(self):
        """Compact RETURN list matches spec exactly."""
        cypher, _ = self._build()
        for col in [
            "m.id AS metabolite_id",
            "m.name AS name",
            "m.formula AS formula",
            "coalesce(m.elements, []) AS elements",
            "m.mass AS mass",
            "coalesce(m.gene_count, 0) AS gene_count",
            "coalesce(m.organism_count, 0) AS organism_count",
            "coalesce(m.transporter_count, 0) AS transporter_count",
            "coalesce(m.evidence_sources, []) AS evidence_sources",
            "m.chebi_id AS chebi_id",
            "coalesce(m.pathway_ids, []) AS pathway_ids",
            "coalesce(m.pathway_count, 0) AS pathway_count",
        ]:
            assert col in cypher, f"missing compact column: {col}"
        # verbose-only columns should NOT appear in compact mode
        assert "inchikey" not in cypher
        assert "smiles" not in cypher
        assert "pathway_names" not in cypher

    def test_returns_verbose_columns(self):
        """Verbose adds inchikey, smiles, mnxm_id, hmdb_id, pathway_names —
        all direct property reads on m."""
        cypher, _ = self._build(verbose=True)
        for col in [
            "m.inchikey AS inchikey",
            "m.smiles AS smiles",
            "m.mnxm_id AS mnxm_id",
            "m.hmdb_id AS hmdb_id",
            "coalesce(m.pathway_names, []) AS pathway_names",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_verbose_has_no_call_subqueries(self):
        """Guard: verbose mode must NOT introduce per-row CALL subqueries.
        Verbose stays 100% property reads (no edge traversal)."""
        cypher, _ = self._build(verbose=True)
        # No CALL { } subqueries in detail builder
        assert "CALL {" not in cypher
        assert "CALL{" not in cypher

    def test_order_by(self):
        """No-search ORDER BY: organism_count DESC, gene_count DESC, m.id."""
        cypher, _ = self._build()
        assert (
            "ORDER BY m.organism_count DESC, m.gene_count DESC, m.id"
            in cypher
        )

    def test_order_by_with_search(self):
        """Search variant ORDER BY: score DESC, organism_count DESC, m.id."""
        cypher, _ = self._build(search_text="glucose")
        assert "ORDER BY score DESC, m.organism_count DESC, m.id" in cypher

    def test_limit_and_offset_clauses(self):
        cypher, params = self._build(limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_per_row_pathway_count_is_property_read(self):
        """pathway_count comes from coalesce(m.pathway_count, 0) — not size()."""
        cypher, _ = self._build()
        assert "coalesce(m.pathway_count, 0) AS pathway_count" in cypher

    def test_no_edge_traversal_in_filters(self):
        """Guard against regressing to pre-KG-A5..A8 form: no per-row
        EXISTS{ MATCH ... } against Metabolite_in_pathway or
        Organism_has_metabolite. All filters operate on flattened
        denormalized array properties on the Metabolite node."""
        cypher, _ = self._build(
            organism_names_lc=["prochlorococcus med4"],
            pathway_ids=["kegg.pathway:ko00910"],
        )
        assert "Metabolite_in_pathway" not in cypher
        assert "Organism_has_metabolite" not in cypher
        # No EXISTS subquery patterns either
        assert "EXISTS {" not in cypher
        assert "EXISTS{" not in cypher


class TestBuildListMetabolitesSummary:
    """Envelope-builder tests for list_metabolites."""

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_list_metabolites_summary,
        )
        return build_list_metabolites_summary(**kwargs)

    def test_no_filters(self):
        cypher, params = self._build()
        assert "MATCH (m:Metabolite)" in cypher
        assert "total_entries" in cypher
        assert "total_matching" in cypher
        assert params == {}

    def test_with_filters(self):
        """Filters propagate into params + WHERE clause."""
        cypher, params = self._build(elements=["N"])
        assert (
            "ALL(e IN $elements WHERE e IN coalesce(m.elements, []))"
            in cypher
        )
        assert params["elements"] == ["N"]

    def test_shares_where_clause(self):
        """Same _list_metabolites_where() helper as detail builder —
        organism_names_lc filter renders identically."""
        cypher, params = self._build(
            organism_names_lc=["prochlorococcus med4"])
        assert (
            "ANY(o IN coalesce(m.organism_names, []) "
            "WHERE toLower(o) IN $organism_names_lc)"
            in cypher
        )
        assert params["organism_names_lc"] == ["prochlorococcus med4"]

    def test_returns_envelope_columns(self):
        """Summary RETURN includes envelope keys: total_entries,
        total_matching, top_organisms, top_metabolite_pathways,
        by_evidence_source, with_chebi/with_hmdb/with_mnxm,
        mass_min/median/max."""
        cypher, _ = self._build()
        for key in [
            "total_entries",
            "total_matching",
            "top_organisms",
            "top_metabolite_pathways",
            "by_evidence_source",
            "with_chebi",
            "with_hmdb",
            "with_mnxm",
            "mass_min",
            "mass_median",
            "mass_max",
        ]:
            assert key in cypher, f"missing envelope column: {key}"

    def test_does_not_collect_metabolite_nodes(self):
        """Memory-friendly guard: never `collect(m) AS matched`. Should
        flatten `m.organism_names` / `m.pathway_ids` instead."""
        cypher, _ = self._build()
        assert "collect(m) AS matched" not in cypher
        assert "collect(m)AS matched" not in cypher

    def test_top_organisms_uses_apoc_frequencies(self):
        """top_organisms uses apoc.coll.frequencies + UNWIND + ORDER BY DESC + LIMIT 10."""
        cypher, _ = self._build()
        assert "apoc.coll.frequencies(all_orgs)" in cypher
        # The top-10 in-Cypher trim
        assert "UNWIND" in cypher
        assert "ORDER BY count DESC" in cypher
        assert "LIMIT 10" in cypher

    def test_top_pathways_uses_keggterm_lookup(self):
        """top_pathways block does an OPTIONAL MATCH (p:KeggTerm) inside
        a CALL to look up pathway_name."""
        cypher, _ = self._build()
        assert "OPTIONAL MATCH (p:KeggTerm" in cypher
        assert "pathway_name" in cypher
        assert "CALL {" in cypher or "CALL{" in cypher

    def test_search_adds_score_columns(self):
        """Search variant adds score_max + score_median to the envelope
        via apoc.coll.max + apoc.coll.sort + median index."""
        cypher, params = self._build(search_text="glucose")
        assert "metaboliteFullText" in cypher
        assert "score_max" in cypher
        assert "score_median" in cypher
        assert "apoc.coll.max(scores)" in cypher
        assert "apoc.coll.sort(scores)" in cypher
        assert params["search"] == "glucose"


# ---------------------------------------------------------------------------
# genes_by_metabolite — Phase 1 (Stage 1 RED)
# ---------------------------------------------------------------------------


class TestBuildGenesByMetaboliteMetabolism:
    """Detail-builder tests for the metabolism arm of genes_by_metabolite.

    Imports happen inside each test so pre-impl test collection still passes.
    """

    _METS = ["kegg.compound:C00086"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_metabolite_metabolism,
        )
        kwargs.setdefault("metabolite_ids", self._METS)
        kwargs.setdefault("organism", self._ORG)
        return build_genes_by_metabolite_metabolism(**kwargs)

    def test_match_path_metabolism_arm(self):
        """Metabolism arm: Gene → Reaction → Metabolite."""
        cypher, _ = self._build()
        assert (
            "(g:Gene)-[:Gene_catalyzes_reaction]->"
            "(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)"
            in cypher
        )

    def test_metabolite_ids_in_where(self):
        cypher, params = self._build()
        assert "m.id IN $metabolite_ids" in cypher
        assert params["metabolite_ids"] == self._METS

    def test_organism_fuzzy_word_match_in_where(self):
        """Mirrors the differential_expression_by_gene fuzzy organism match."""
        cypher, params = self._build()
        assert "split(toLower($organism), ' ')" in cypher
        assert "toLower(g.organism_name) CONTAINS word" in cypher
        # Wrapped in ALL(...) so all input words must be present
        assert "ALL(word IN split" in cypher
        assert params["organism"] == self._ORG

    def test_ec_numbers_filter(self):
        cypher, params = self._build(ec_numbers=["6.3.1.2"])
        assert (
            "ANY(ec IN $ec_numbers WHERE ec IN coalesce(r.ec_numbers, []))"
            in cypher
        )
        assert params["ec_numbers"] == ["6.3.1.2"]

    def test_mass_balance_filter(self):
        cypher, params = self._build(mass_balance="balanced")
        assert "r.mass_balance = $mass_balance" in cypher
        assert params["mass_balance"] == "balanced"

    def test_metabolite_pathway_ids_filter(self):
        cypher, params = self._build(
            metabolite_pathway_ids=["kegg.pathway:ko00910"],
        )
        assert (
            "ANY(p IN $metabolite_pathway_ids "
            "WHERE p IN coalesce(m.pathway_ids, []))"
            in cypher
        )
        assert params["metabolite_pathway_ids"] == ["kegg.pathway:ko00910"]

    def test_gene_categories_filter(self):
        cypher, params = self._build(gene_categories=["Transport"])
        assert "g.gene_category IN $gene_categories" in cypher
        assert params["gene_categories"] == ["Transport"]

    def test_compact_return_columns(self):
        """Compact RETURN list per spec — 13 entries plus the two
        per-arm-null padding columns (transport_confidence, tcdb_*)."""
        cypher, _ = self._build()
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "g.product AS product",
            "'metabolism' AS evidence_source",
            "null AS transport_confidence",
            "r.id AS reaction_id",
            "r.name AS reaction_name",
            "coalesce(r.ec_numbers, []) AS ec_numbers",
            "r.mass_balance AS mass_balance",
            "null AS tcdb_family_id",
            "null AS tcdb_family_name",
            "m.id AS metabolite_id",
            "m.name AS metabolite_name",
            "m.formula AS metabolite_formula",
            "m.mass AS metabolite_mass",
            "m.chebi_id AS metabolite_chebi_id",
        ]:
            assert col in cypher, f"missing compact column: {col}"
        # verbose-only columns absent in compact mode
        assert "metabolite_inchikey" not in cypher
        assert "reaction_mnxr_id" not in cypher
        assert "tcdb_level_kind" not in cypher

    def test_verbose_return_columns(self):
        cypher, _ = self._build(verbose=True)
        for col in [
            "g.gene_category AS gene_category",
            "m.inchikey AS metabolite_inchikey",
            "m.smiles AS metabolite_smiles",
            "m.mnxm_id AS metabolite_mnxm_id",
            "m.hmdb_id AS metabolite_hmdb_id",
            "r.mnxr_id AS reaction_mnxr_id",
            "r.rhea_ids AS reaction_rhea_ids",
            "null AS tcdb_level_kind",
            "null AS tc_class_id",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_order_by(self):
        """Per spec: ORDER BY metabolite_id, reaction_id, locus_tag."""
        cypher, _ = self._build()
        assert "ORDER BY metabolite_id, reaction_id, locus_tag" in cypher

    def test_limit_and_offset_clauses(self):
        cypher, params = self._build(limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_no_transport_confidence_param(self):
        """Metabolism arm must not accept transport_confidence — that is
        a transport-arm-only filter per the per-arm filter scope rule."""
        with pytest.raises(TypeError):
            self._build(transport_confidence="substrate_confirmed")


class TestBuildGenesByMetaboliteTransport:
    """Detail-builder tests for the transport arm of genes_by_metabolite."""

    _METS = ["kegg.compound:C00086"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_metabolite_transport,
        )
        kwargs.setdefault("metabolite_ids", self._METS)
        kwargs.setdefault("organism", self._ORG)
        return build_genes_by_metabolite_transport(**kwargs)

    def test_match_path_transport_arm(self):
        """Transport arm: Gene → TcdbFamily → Metabolite (single-hop, post-rollup)."""
        cypher, _ = self._build()
        assert (
            "(g:Gene)-[:Gene_has_tcdb_family]->"
            "(tf:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)"
            in cypher
        )

    def test_metabolite_ids_in_where(self):
        cypher, params = self._build()
        assert "m.id IN $metabolite_ids" in cypher
        assert params["metabolite_ids"] == self._METS

    def test_organism_fuzzy_word_match_in_where(self):
        cypher, params = self._build()
        assert "split(toLower($organism), ' ')" in cypher
        assert "toLower(g.organism_name) CONTAINS word" in cypher
        assert params["organism"] == self._ORG

    def test_metabolite_pathway_ids_filter(self):
        cypher, params = self._build(
            metabolite_pathway_ids=["kegg.pathway:ko00910"],
        )
        assert (
            "ANY(p IN $metabolite_pathway_ids "
            "WHERE p IN coalesce(m.pathway_ids, []))"
            in cypher
        )
        assert params["metabolite_pathway_ids"] == ["kegg.pathway:ko00910"]

    def test_gene_categories_filter(self):
        cypher, params = self._build(gene_categories=["Transport"])
        assert "g.gene_category IN $gene_categories" in cypher
        assert params["gene_categories"] == ["Transport"]

    def test_transport_confidence_substrate_confirmed(self):
        """substrate_confirmed → tf.level_kind = 'tc_specificity'."""
        cypher, _ = self._build(transport_confidence="substrate_confirmed")
        assert "tf.level_kind = 'tc_specificity'" in cypher

    def test_transport_confidence_family_inferred(self):
        """family_inferred → tf.level_kind <> 'tc_specificity'."""
        cypher, _ = self._build(transport_confidence="family_inferred")
        assert "tf.level_kind <> 'tc_specificity'" in cypher

    def test_no_transport_confidence_filter_when_none(self):
        """Default (no transport_confidence) → no level_kind WHERE clause.

        The substring `tf.level_kind = 'tc_specificity'` legitimately appears
        twice in the unconditional cypher (RETURN CASE + ORDER BY CASE per
        spec), so substring-absence is too coarse. We pin: WHERE block has
        no level_kind predicate; the substring count stays at 2 in default
        mode (vs. 3 when `transport_confidence='substrate_confirmed'` adds a
        WHERE clause).
        """
        cypher, _ = self._build()
        where_block = cypher.split("RETURN")[0]
        assert "tf.level_kind" not in where_block
        assert cypher.count("tf.level_kind = 'tc_specificity'") == 2
        assert "tf.level_kind <> 'tc_specificity'" not in cypher

    def test_no_metabolism_filters(self):
        """Transport arm must not accept metabolism-arm-only filters."""
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_metabolite_transport,
        )
        with pytest.raises(TypeError):
            build_genes_by_metabolite_transport(
                metabolite_ids=self._METS,
                organism=self._ORG,
                ec_numbers=["6.3.1.2"],
            )
        with pytest.raises(TypeError):
            build_genes_by_metabolite_transport(
                metabolite_ids=self._METS,
                organism=self._ORG,
                mass_balance="balanced",
            )

    def test_compact_return_columns(self):
        cypher, _ = self._build()
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "g.product AS product",
            "'transport' AS evidence_source",
            "tf.id AS tcdb_family_id",
            "tf.name AS tcdb_family_name",
            "null AS reaction_id",
            "null AS reaction_name",
            "null AS ec_numbers",
            "null AS mass_balance",
            "m.id AS metabolite_id",
            "m.name AS metabolite_name",
            "m.formula AS metabolite_formula",
            "m.mass AS metabolite_mass",
            "m.chebi_id AS metabolite_chebi_id",
        ]:
            assert col in cypher, f"missing compact column: {col}"
        # verbose-only absent
        assert "metabolite_inchikey" not in cypher
        assert "tcdb_level_kind" not in cypher

    def test_verbose_return_columns(self):
        cypher, _ = self._build(verbose=True)
        for col in [
            "g.gene_category AS gene_category",
            "m.inchikey AS metabolite_inchikey",
            "m.smiles AS metabolite_smiles",
            "m.mnxm_id AS metabolite_mnxm_id",
            "m.hmdb_id AS metabolite_hmdb_id",
            "tf.level_kind AS tcdb_level_kind",
            "tf.tc_class_id AS tc_class_id",
            "null AS reaction_mnxr_id",
            "null AS reaction_rhea_ids",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_transport_confidence_case_expression_in_return(self):
        """`transport_confidence` is a derived column from level_kind."""
        cypher, _ = self._build()
        # Per spec:
        #   CASE WHEN tf.level_kind = 'tc_specificity'
        #        THEN 'substrate_confirmed' ELSE 'family_inferred' END AS transport_confidence
        assert "tf.level_kind = 'tc_specificity'" in cypher
        assert "'substrate_confirmed'" in cypher
        assert "'family_inferred'" in cypher
        assert "AS transport_confidence" in cypher

    def test_order_by_substrate_confirmed_first(self):
        """Per spec: ORDER BY metabolite_id, CASE…tc_specificity = 0 else 1,
        tcdb_family_id, locus_tag — ensures substrate_confirmed transports
        sort ahead of family_inferred within each metabolite group."""
        cypher, _ = self._build()
        assert "ORDER BY metabolite_id" in cypher
        # The CASE-on-tc_specificity inside ORDER BY block
        assert "CASE WHEN tf.level_kind = 'tc_specificity' THEN 0 ELSE 1 END" in cypher
        assert "tcdb_family_id" in cypher
        assert "locus_tag" in cypher

    def test_limit_and_offset_clauses(self):
        cypher, params = self._build(limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5


class TestBuildGenesByMetaboliteSummary:
    """Single-pass envelope-builder tests for genes_by_metabolite."""

    _METS = ["kegg.compound:C00086"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_metabolite_summary,
        )
        kwargs.setdefault("metabolite_ids", self._METS)
        kwargs.setdefault("organism", self._ORG)
        return build_genes_by_metabolite_summary(**kwargs)

    def test_unioned_match_paths_present(self):
        """Both arms appear inside a CALL{...UNION...} subquery —
        the only place a UNION is allowed (detail uses two arms api-side)."""
        cypher, _ = self._build()
        # Both MATCH paths
        assert (
            "(g:Gene)-[:Gene_catalyzes_reaction]->"
            "(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)"
            in cypher
        )
        assert (
            "(g:Gene)-[:Gene_has_tcdb_family]->"
            "(tf:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)"
            in cypher
        )
        assert "UNION" in cypher

    def test_returns_envelope_keys(self):
        """Per spec § build_genes_by_metabolite_summary."""
        cypher, _ = self._build()
        for key in [
            "total_matching",
            "gene_count_total",
            "reaction_count_total",
            "transporter_count_total",
            "metabolite_count_total",
            "rows_by_evidence_source",
            "rows_by_transport_confidence",
            "by_metabolite",
            "top_reactions",
            "top_tcdb_families",
            "top_gene_categories",
            "top_genes",
        ]:
            assert key in cypher, f"missing envelope key: {key}"

    def test_metabolite_ids_in_params(self):
        cypher, params = self._build()
        assert "m.id IN $metabolite_ids" in cypher
        assert params["metabolite_ids"] == self._METS

    def test_organism_fuzzy_match_in_params(self):
        cypher, params = self._build()
        assert "split(toLower($organism), ' ')" in cypher
        assert params["organism"] == self._ORG

    def test_metabolism_only_filters_propagate_to_metabolism_arm(self):
        """ec_numbers / mass_balance reach the WHERE block — and only the
        metabolism side of the UNION carries them (transport arm runs unfiltered)."""
        cypher, params = self._build(
            ec_numbers=["6.3.1.2"], mass_balance="balanced",
        )
        assert "$ec_numbers" in cypher
        assert "$mass_balance" in cypher
        assert params["ec_numbers"] == ["6.3.1.2"]
        assert params["mass_balance"] == "balanced"

    def test_transport_only_filter_propagates_to_transport_arm(self):
        """transport_confidence reaches the WHERE block (transport-arm only)."""
        cypher, _ = self._build(transport_confidence="substrate_confirmed")
        assert "tf.level_kind = 'tc_specificity'" in cypher

    def test_uniform_filters_propagate_to_both_arms(self):
        """metabolite_pathway_ids and gene_categories narrow both arms."""
        cypher, params = self._build(
            metabolite_pathway_ids=["kegg.pathway:ko00910"],
            gene_categories=["Transport"],
        )
        assert "$metabolite_pathway_ids" in cypher
        assert "$gene_categories" in cypher
        assert params["metabolite_pathway_ids"] == ["kegg.pathway:ko00910"]
        assert params["gene_categories"] == ["Transport"]

    def test_arms_filter_skips_metabolism_arm(self):
        """arms=('transport',) suppresses the metabolism arm of the UNION."""
        cypher, _ = self._build(arms=("transport",))
        # Transport arm present
        assert "Gene_has_tcdb_family" in cypher
        # Metabolism arm path absent
        assert "Gene_catalyzes_reaction" not in cypher

    def test_arms_filter_skips_transport_arm(self):
        """arms=('metabolism',) suppresses the transport arm of the UNION."""
        cypher, _ = self._build(arms=("metabolism",))
        assert "Gene_catalyzes_reaction" in cypher
        assert "Gene_has_tcdb_family" not in cypher


# ---------------------------------------------------------------------------
# metabolites_by_gene (MBG) — Tool 3 of the chemistry slice-1 symmetric set
#
# Mirrors the GBM test classes (above), with these MBG-specific changes:
#   - anchor flips to locus_tags + organism (single-organism enforced)
#   - new metabolite_elements filter (uniform across both arms)
#   - per-arm filter scope identical to GBM (ec_numbers / mass_balance →
#     metabolism only; transport_confidence → transport only;
#     metabolite_pathway_ids / gene_categories / metabolite_ids /
#     metabolite_elements → uniform across both arms)
#   - sort uses **global precision-tier** (metabolism → transport_substrate_
#     confirmed → transport_family_inferred), then input-gene order, then
#     locus_tag, then metabolite_id
#   - summary builder gains two new envelope keys: by_element + top_pathways
#
# Spec: docs/tool-specs/metabolites_by_gene.md
# ---------------------------------------------------------------------------


class TestBuildMetabolitesByGeneMetabolism:
    """Detail-builder tests for the metabolism arm of metabolites_by_gene.

    Imports happen inside each test so pre-impl test collection still passes.
    """

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_metabolites_by_gene_metabolism,
        )
        kwargs.setdefault("locus_tags", self._LOCUS)
        kwargs.setdefault("organism", self._ORG)
        return build_metabolites_by_gene_metabolism(**kwargs)

    def test_match_path_metabolism_arm(self):
        """Metabolism arm: Gene → Reaction → Metabolite (mirror GBM)."""
        cypher, _ = self._build()
        assert (
            "(g:Gene)-[:Gene_catalyzes_reaction]->"
            "(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)"
            in cypher
        )

    def test_locus_tags_in_where(self):
        """Anchor: g.locus_tag IN $locus_tags."""
        cypher, params = self._build()
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == self._LOCUS

    def test_organism_fuzzy_word_match_in_where(self):
        """Mirrors the differential_expression_by_gene + GBM fuzzy organism match."""
        cypher, params = self._build()
        assert "split(toLower($organism), ' ')" in cypher
        assert "toLower(g.organism_name) CONTAINS word" in cypher
        # All input words must match
        assert "ALL(word IN split" in cypher
        assert params["organism"] == self._ORG

    def test_ec_numbers_filter(self):
        cypher, params = self._build(ec_numbers=["3.5.1.5"])
        assert (
            "ANY(ec IN $ec_numbers WHERE ec IN coalesce(r.ec_numbers, []))"
            in cypher
        )
        assert params["ec_numbers"] == ["3.5.1.5"]

    def test_mass_balance_filter(self):
        cypher, params = self._build(mass_balance="balanced")
        assert "r.mass_balance = $mass_balance" in cypher
        assert params["mass_balance"] == "balanced"

    def test_metabolite_pathway_ids_filter(self):
        """Anchored on m.pathway_ids (KG-A5 denorm); applies uniformly."""
        cypher, params = self._build(
            metabolite_pathway_ids=["kegg.pathway:ko00910"],
        )
        assert (
            "ANY(p IN $metabolite_pathway_ids "
            "WHERE p IN coalesce(m.pathway_ids, []))"
            in cypher
        )
        assert params["metabolite_pathway_ids"] == ["kegg.pathway:ko00910"]

    def test_gene_categories_filter(self):
        cypher, params = self._build(gene_categories=["Transport"])
        assert "g.gene_category IN $gene_categories" in cypher
        assert params["gene_categories"] == ["Transport"]

    def test_metabolite_ids_filter_uniform(self):
        """metabolite_ids applies to BOTH arms uniformly (per-arm scope)."""
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00086"],
        )
        assert "m.id IN $metabolite_ids" in cypher
        assert params["metabolite_ids"] == ["kegg.compound:C00086"]

    def test_metabolite_elements_filter_uniform(self):
        """NEW MBG filter: metabolite_elements (AND-of-presence on m.elements)."""
        cypher, params = self._build(metabolite_elements=["N"])
        assert (
            "ALL(elem IN $metabolite_elements "
            "WHERE elem IN coalesce(m.elements, []))"
            in cypher
        )
        assert params["metabolite_elements"] == ["N"]

    def test_metabolite_elements_filter_multi(self):
        """`['N', 'P']` requires both elements present (AND semantics)."""
        cypher, params = self._build(metabolite_elements=["N", "P"])
        assert (
            "ALL(elem IN $metabolite_elements "
            "WHERE elem IN coalesce(m.elements, []))"
            in cypher
        )
        assert params["metabolite_elements"] == ["N", "P"]

    def test_compact_return_columns(self):
        """Compact RETURN list — same shape as GBM compact mode (15 fields
        + per-arm-null padding columns to align with the transport arm)."""
        cypher, _ = self._build()
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "g.product AS product",
            "'metabolism' AS evidence_source",
            "null AS transport_confidence",
            "r.id AS reaction_id",
            "r.name AS reaction_name",
            "coalesce(r.ec_numbers, []) AS ec_numbers",
            "r.mass_balance AS mass_balance",
            "null AS tcdb_family_id",
            "null AS tcdb_family_name",
            "m.id AS metabolite_id",
            "m.name AS metabolite_name",
            "m.formula AS metabolite_formula",
            "m.mass AS metabolite_mass",
            "m.chebi_id AS metabolite_chebi_id",
        ]:
            assert col in cypher, f"missing compact column: {col}"
        # verbose-only columns absent in compact mode
        assert "metabolite_inchikey" not in cypher
        assert "reaction_mnxr_id" not in cypher
        assert "tcdb_level_kind" not in cypher

    def test_verbose_return_columns(self):
        cypher, _ = self._build(verbose=True)
        for col in [
            "g.gene_category AS gene_category",
            "m.inchikey AS metabolite_inchikey",
            "m.smiles AS metabolite_smiles",
            "m.mnxm_id AS metabolite_mnxm_id",
            "m.hmdb_id AS metabolite_hmdb_id",
            "r.mnxr_id AS reaction_mnxr_id",
            "r.rhea_ids AS reaction_rhea_ids",
            "null AS tcdb_level_kind",
            "null AS tc_class_id",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_order_by_precision_tier_then_input_index(self):
        """Per spec § Sort order: detail rows sorted by precision_tier
        (metabolism = 0), then by input gene order via apoc.coll.indexOf,
        then locus_tag, then metabolite_id.

        Metabolism arm precision_tier is constant 0 (substrate-confirmed by
        definition), so the metabolism-arm builder should still emit the
        precision-tier expression for sort consistency with the transport
        arm — or at minimum, sort by input gene index then locus_tag /
        metabolite_id. We pin the input-index expression as load-bearing.
        """
        cypher, _ = self._build()
        # Input-gene-order term — spec § Sort order step 2
        assert "apoc.coll.indexOf($locus_tags" in cypher
        # Stable secondary / tertiary order
        assert "locus_tag" in cypher
        assert "metabolite_id" in cypher

    def test_limit_and_offset_clauses(self):
        cypher, params = self._build(limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_no_transport_confidence_param(self):
        """Per per-arm filter scope rule: metabolism arm does NOT accept
        transport_confidence — that's a transport-arm-only filter."""
        with pytest.raises(TypeError):
            self._build(transport_confidence="substrate_confirmed")


class TestBuildMetabolitesByGeneTransport:
    """Detail-builder tests for the transport arm of metabolites_by_gene."""

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_metabolites_by_gene_transport,
        )
        kwargs.setdefault("locus_tags", self._LOCUS)
        kwargs.setdefault("organism", self._ORG)
        return build_metabolites_by_gene_transport(**kwargs)

    def test_match_path_transport_arm(self):
        """Transport arm: Gene → TcdbFamily → Metabolite (single-hop, post-rollup)."""
        cypher, _ = self._build()
        assert (
            "(g:Gene)-[:Gene_has_tcdb_family]->"
            "(tf:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)"
            in cypher
        )

    def test_locus_tags_in_where(self):
        cypher, params = self._build()
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == self._LOCUS

    def test_organism_fuzzy_word_match_in_where(self):
        cypher, params = self._build()
        assert "split(toLower($organism), ' ')" in cypher
        assert "toLower(g.organism_name) CONTAINS word" in cypher
        assert params["organism"] == self._ORG

    def test_metabolite_pathway_ids_filter(self):
        cypher, params = self._build(
            metabolite_pathway_ids=["kegg.pathway:ko00910"],
        )
        assert (
            "ANY(p IN $metabolite_pathway_ids "
            "WHERE p IN coalesce(m.pathway_ids, []))"
            in cypher
        )
        assert params["metabolite_pathway_ids"] == ["kegg.pathway:ko00910"]

    def test_gene_categories_filter(self):
        cypher, params = self._build(gene_categories=["Transport"])
        assert "g.gene_category IN $gene_categories" in cypher
        assert params["gene_categories"] == ["Transport"]

    def test_metabolite_ids_filter_uniform(self):
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00086"],
        )
        assert "m.id IN $metabolite_ids" in cypher
        assert params["metabolite_ids"] == ["kegg.compound:C00086"]

    def test_metabolite_elements_filter_uniform(self):
        """metabolite_elements applies uniformly to BOTH arms."""
        cypher, params = self._build(metabolite_elements=["N"])
        assert (
            "ALL(elem IN $metabolite_elements "
            "WHERE elem IN coalesce(m.elements, []))"
            in cypher
        )
        assert params["metabolite_elements"] == ["N"]

    def test_transport_confidence_substrate_confirmed(self):
        """substrate_confirmed → tf.level_kind = 'tc_specificity'."""
        cypher, _ = self._build(transport_confidence="substrate_confirmed")
        assert "tf.level_kind = 'tc_specificity'" in cypher

    def test_transport_confidence_family_inferred(self):
        """family_inferred → tf.level_kind <> 'tc_specificity'."""
        cypher, _ = self._build(transport_confidence="family_inferred")
        assert "tf.level_kind <> 'tc_specificity'" in cypher

    def test_no_transport_confidence_filter_when_none(self):
        """Default (no transport_confidence) → no level_kind WHERE clause.

        Mirrors the GBM transport-arm contract: the substring
        `tf.level_kind = 'tc_specificity'` legitimately appears twice in
        unconditional cypher (RETURN CASE + ORDER BY CASE per spec).
        """
        cypher, _ = self._build()
        where_block = cypher.split("RETURN")[0]
        assert "tf.level_kind" not in where_block
        assert "tf.level_kind <> 'tc_specificity'" not in cypher

    def test_no_metabolism_filters(self):
        """Per per-arm filter scope: transport arm rejects ec_numbers /
        mass_balance with TypeError."""
        from multiomics_explorer.kg.queries_lib import (
            build_metabolites_by_gene_transport,
        )
        with pytest.raises(TypeError):
            build_metabolites_by_gene_transport(
                locus_tags=self._LOCUS,
                organism=self._ORG,
                ec_numbers=["3.5.1.5"],
            )
        with pytest.raises(TypeError):
            build_metabolites_by_gene_transport(
                locus_tags=self._LOCUS,
                organism=self._ORG,
                mass_balance="balanced",
            )

    def test_compact_return_columns(self):
        cypher, _ = self._build()
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "g.product AS product",
            "'transport' AS evidence_source",
            "tf.id AS tcdb_family_id",
            "tf.name AS tcdb_family_name",
            "null AS reaction_id",
            "null AS reaction_name",
            "null AS ec_numbers",
            "null AS mass_balance",
            "m.id AS metabolite_id",
            "m.name AS metabolite_name",
            "m.formula AS metabolite_formula",
            "m.mass AS metabolite_mass",
            "m.chebi_id AS metabolite_chebi_id",
        ]:
            assert col in cypher, f"missing compact column: {col}"
        # verbose-only absent
        assert "metabolite_inchikey" not in cypher
        assert "tcdb_level_kind" not in cypher

    def test_verbose_return_columns(self):
        cypher, _ = self._build(verbose=True)
        for col in [
            "g.gene_category AS gene_category",
            "m.inchikey AS metabolite_inchikey",
            "m.smiles AS metabolite_smiles",
            "m.mnxm_id AS metabolite_mnxm_id",
            "m.hmdb_id AS metabolite_hmdb_id",
            "tf.level_kind AS tcdb_level_kind",
            "tf.tc_class_id AS tc_class_id",
            "null AS reaction_mnxr_id",
            "null AS reaction_rhea_ids",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_transport_confidence_case_expression_in_return(self):
        """`transport_confidence` is a derived column from level_kind."""
        cypher, _ = self._build()
        assert "tf.level_kind = 'tc_specificity'" in cypher
        assert "'substrate_confirmed'" in cypher
        assert "'family_inferred'" in cypher
        assert "AS transport_confidence" in cypher

    def test_order_by_uses_input_index(self):
        """Per MBG spec: ORDER BY uses apoc.coll.indexOf($locus_tags, ...)
        for input-gene-order. Transport arm's per-precision sort is
        substrate_confirmed-first within the transport tier."""
        cypher, _ = self._build()
        # Input-gene-order term — load-bearing for the global merge in api/
        assert "apoc.coll.indexOf($locus_tags" in cypher
        # substrate_confirmed-first ordering inside transport tier
        assert (
            "CASE WHEN tf.level_kind = 'tc_specificity' THEN 0 ELSE 1 END"
            in cypher
        )

    def test_limit_and_offset_clauses(self):
        cypher, params = self._build(limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5


class TestBuildMetabolitesByGeneSummary:
    """Single-pass envelope-builder tests for metabolites_by_gene.

    Mirrors GBM's summary-builder contract, plus two new envelope keys:
    by_element and top_pathways.
    """

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_metabolites_by_gene_summary,
        )
        kwargs.setdefault("locus_tags", self._LOCUS)
        kwargs.setdefault("organism", self._ORG)
        return build_metabolites_by_gene_summary(**kwargs)

    def test_unioned_match_paths_present(self):
        """Both arms appear inside a CALL{...UNION...} subquery."""
        cypher, _ = self._build()
        assert (
            "(g:Gene)-[:Gene_catalyzes_reaction]->"
            "(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)"
            in cypher
        )
        assert (
            "(g:Gene)-[:Gene_has_tcdb_family]->"
            "(tf:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)"
            in cypher
        )
        assert "UNION" in cypher

    def test_returns_envelope_keys(self):
        """Per spec § build_metabolites_by_gene_summary RETURN keys.

        MBG envelope mirrors GBM but flips per-entity rollups (by_gene
        instead of by_metabolite, top_metabolites instead of top_genes)
        and adds two new keys: top_metabolite_pathways + by_element.
        """
        cypher, _ = self._build()
        for key in [
            "total_matching",
            "gene_count_total",
            "reaction_count_total",
            "transporter_count_total",
            "metabolite_count_total",
            "rows_by_evidence_source",
            "rows_by_transport_confidence",
            "by_gene",
            "top_reactions",
            "top_tcdb_families",
            "top_gene_categories",
            "top_metabolites",
            "top_metabolite_pathways",
            "by_element",
        ]:
            assert key in cypher, f"missing envelope key: {key}"

    def test_locus_tags_in_params(self):
        cypher, params = self._build()
        assert "g.locus_tag IN $locus_tags" in cypher
        assert params["locus_tags"] == self._LOCUS

    def test_organism_fuzzy_match_in_params(self):
        cypher, params = self._build()
        assert "split(toLower($organism), ' ')" in cypher
        assert params["organism"] == self._ORG

    def test_metabolism_only_filters_propagate_to_metabolism_arm(self):
        """ec_numbers / mass_balance reach only the metabolism arm WHERE."""
        cypher, params = self._build(
            ec_numbers=["3.5.1.5"], mass_balance="balanced",
        )
        assert "$ec_numbers" in cypher
        assert "$mass_balance" in cypher
        assert params["ec_numbers"] == ["3.5.1.5"]
        assert params["mass_balance"] == "balanced"

    def test_transport_only_filter_propagates_to_transport_arm(self):
        """transport_confidence reaches only the transport arm WHERE."""
        cypher, _ = self._build(transport_confidence="substrate_confirmed")
        assert "tf.level_kind = 'tc_specificity'" in cypher

    def test_uniform_filters_propagate_to_both_arms(self):
        """metabolite_pathway_ids, gene_categories, metabolite_ids,
        metabolite_elements all narrow both arms uniformly."""
        cypher, params = self._build(
            metabolite_pathway_ids=["kegg.pathway:ko00910"],
            gene_categories=["Transport"],
            metabolite_ids=["kegg.compound:C00086"],
            metabolite_elements=["N"],
        )
        assert "$metabolite_pathway_ids" in cypher
        assert "$gene_categories" in cypher
        assert "$metabolite_ids" in cypher
        assert "$metabolite_elements" in cypher
        assert params["metabolite_pathway_ids"] == ["kegg.pathway:ko00910"]
        assert params["gene_categories"] == ["Transport"]
        assert params["metabolite_ids"] == ["kegg.compound:C00086"]
        assert params["metabolite_elements"] == ["N"]

    def test_arms_filter_skips_metabolism_arm(self):
        """arms=('transport',) suppresses the metabolism arm of the UNION."""
        cypher, _ = self._build(arms=("transport",))
        assert "Gene_has_tcdb_family" in cypher
        assert "Gene_catalyzes_reaction" not in cypher

    def test_arms_filter_skips_transport_arm(self):
        """arms=('metabolism',) suppresses the transport arm of the UNION."""
        cypher, _ = self._build(arms=("metabolism",))
        assert "Gene_catalyzes_reaction" in cypher
        assert "Gene_has_tcdb_family" not in cypher

    def test_top_pathways_chemistry_filter(self):
        """top_pathways must apply the `p.reaction_count >= 3` chemistry
        filter (spec § verified Cypher example 5). Without this,
        signaling/disease pathways with 1-2 reactions would dominate."""
        cypher, _ = self._build()
        assert "p.reaction_count" in cypher
        assert ">= 3" in cypher

    def test_by_element_uses_metabolite_elements_field(self):
        """by_element rollup unwinds m.elements (KG-A3 Hill-parsed
        presence list). Per spec § verified Cypher example 6."""
        cypher, _ = self._build()
        assert "m.elements" in cypher


# ===========================================================================
# Cluster A — F1 informativeness surface (frozen spec 2026-05-04)
# ===========================================================================
# These tests pin the new behaviors from cluster-a-f1-surface.md:
# A2 surface additions across 5 builders (gene_overview + 4 ontology tools).
#
# - gene_overview (gene side): RETURN adds annotation_state +
#   informative_annotation_types; summary builder gets `by_annotation_state`.
# - gene_ontology_terms (term side, template): adds informative_only param +
#   `is_informative` row column.
# - genes_by_ontology (term side, per-builder split per spec table).
# - search_ontology (term side): adds informative_only + `is_informative`.
# - ontology_landscape (term side, default-on filter, no row column).


class TestBuildGeneOverviewF1Surface:
    """gene_overview detail: adds annotation_state + informative_annotation_types."""

    def test_compact_return_includes_annotation_state(self):
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"])
        assert "g.annotation_state AS annotation_state" in cypher

    def test_compact_return_includes_informative_annotation_types(self):
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"])
        # Coalesced to [] since the prop is sparse-default-empty per KG.
        assert "informative_annotation_types" in cypher
        assert "coalesce(g.informative_annotation_types, [])" in cypher

    def test_verbose_still_has_new_columns(self):
        cypher, _ = build_gene_overview(locus_tags=["PMM1428"], verbose=True)
        assert "g.annotation_state AS annotation_state" in cypher
        assert "informative_annotation_types" in cypher


class TestBuildGeneOverviewSummaryF1Surface:
    """gene_overview_summary: adds by_annotation_state envelope rollup."""

    def test_summary_returns_by_annotation_state(self):
        cypher, _ = build_gene_overview_summary(locus_tags=["PMM1428"])
        assert "by_annotation_state" in cypher

    def test_summary_uses_apoc_frequencies_on_annotation_state(self):
        """Spec § Cypher: WITH ..., [g IN found | g.annotation_state] AS states
        RETURN ..., apoc.coll.frequencies(states) AS by_annotation_state."""
        cypher, _ = build_gene_overview_summary(locus_tags=["PMM1428"])
        assert "annotation_state" in cypher
        # frequencies of the annotation_state list expression
        assert "apoc.coll.frequencies" in cypher


class TestBuildGeneOntologyTermsF1Surface:
    """gene_ontology_terms (leaf + rollup builders): informative_only
    filter + is_informative row column."""

    def test_default_is_informative_in_return(self):
        """is_informative column in RETURN — always present (positive framing)."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "is_informative" in cypher
        # Coalesce-from-sparse: 'true'/null on KG → bool via <> 'true'.
        assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_informative_only_default_false_skips_filter(self):
        """Default behavior: informative_only=False ⇒ filter NOT in WHERE."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        # The filter predicate (used as a WHERE condition) should NOT be
        # present when informative_only is False — only the RETURN coercion.
        # Search for the WHERE-side predicate (it won't have AS is_informative).
        # We assert no filter line emits the predicate as an AND-clause.
        assert "AND coalesce(t.is_uninformative, '') <> 'true'" not in cypher
        # default param value
        assert params.get("informative_only") in (None, False)

    def test_informative_only_true_adds_where(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
            informative_only=True,
        )
        # Spec § filter pattern: AND coalesce(t.is_uninformative, '') <> 'true'.
        assert "AND coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_rollup_mode_also_supports_informative_only(self):
        """Rollup mode (walk to ancestors) must thread the same filter."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
            mode="rollup", level=1, informative_only=True,
        )
        assert "AND coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_rollup_mode_returns_is_informative(self):
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
            mode="rollup", level=1,
        )
        assert "is_informative" in cypher


class TestBuildGeneOntologyTermsSummaryF1Surface:
    """gene_ontology_terms_summary: informative_only filter (no row column)."""

    def test_default_does_not_filter(self):
        cypher, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
        )
        assert "AND coalesce(t.is_uninformative, '') <> 'true'" not in cypher

    def test_informative_only_true_adds_where(self):
        cypher, _ = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
            informative_only=True,
        )
        assert "AND coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_rollup_summary_supports_informative_only(self):
        cypher, _ = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="go_bp", organism_name="Test Org",
            mode="rollup", level=1, informative_only=True,
        )
        assert "AND coalesce(t.is_uninformative, '') <> 'true'" in cypher


class TestBuildSearchOntologyF1Surface:
    """search_ontology: informative_only filter + is_informative row column."""

    def test_default_returns_is_informative_column(self):
        cypher, _ = build_search_ontology(ontology="go_bp", search_text="test")
        assert "is_informative" in cypher
        assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_default_does_not_filter(self):
        """informative_only=False (default) ⇒ no filter in WHERE."""
        cypher, _ = build_search_ontology(ontology="go_bp", search_text="test")
        # No predicate-side filter (only the RETURN coercion as `is_informative`).
        # The where-side filter clause must be absent.
        assert "t.is_uninformative" in cypher  # only in RETURN coalesce
        # Confirm there's no standalone WHERE-side filter clause; the only
        # appearance is the RETURN-side coalesce.
        assert cypher.count("coalesce(t.is_uninformative, '') <> 'true'") == 1

    def test_informative_only_true_adds_where_clause(self):
        cypher, _ = build_search_ontology(
            ontology="go_bp", search_text="test", informative_only=True,
        )
        # Now appears at least twice: once in WHERE-side filter, once in RETURN.
        assert cypher.count("coalesce(t.is_uninformative, '') <> 'true'") >= 2

    def test_pfam_union_threads_filter_into_both_branches(self):
        """Pfam uses CALL { ... UNION ALL ... } structure; filter must apply
        in both UNION branches when informative_only=True."""
        cypher, _ = build_search_ontology(
            ontology="pfam", search_text="test", informative_only=True,
        )
        # The filter must appear in both UNION branches AND in the
        # outer RETURN coalesce — so total ≥ 3.
        assert cypher.count("coalesce(t.is_uninformative, '') <> 'true'") >= 3


class TestBuildSearchOntologySummaryF1Surface:
    """search_ontology_summary: informative_only filter (no row column)."""

    def test_default_does_not_filter(self):
        cypher, _ = build_search_ontology_summary(
            ontology="go_bp", search_text="test",
        )
        assert "coalesce(t.is_uninformative, '') <> 'true'" not in cypher

    def test_informative_only_true_adds_where(self):
        cypher, _ = build_search_ontology_summary(
            ontology="go_bp", search_text="test", informative_only=True,
        )
        assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher


class TestBuildGenesByOntologyF1Surface:
    """genes_by_ontology: split per-builder per spec table.

    | Builder | filter | row column |
    |---|---|---|
    | validate | No | No |
    | match-stage helper | Yes (shared) | n/a |
    | detail | inherited | Yes |
    | per_term | inherited | Yes |
    | per_gene | inherited | No |
    """

    # ---- validate: no filter, no row column ---------------------------------
    def test_validate_does_not_emit_filter(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_validate,
        )
        cypher, _ = build_genes_by_ontology_validate(
            term_ids=["go:0006260"], ontology="go_bp", level=1,
        )
        # Validate reports input IDs as-is regardless of informativeness.
        assert "is_uninformative" not in cypher
        assert "is_informative" not in cypher

    # ---- match-stage helper: filter when informative_only=True --------------
    def test_match_stage_default_omits_filter(self):
        from multiomics_explorer.kg.queries_lib import (
            _genes_by_ontology_match_stage,
        )
        cypher, _ = _genes_by_ontology_match_stage(
            ontology="go_bp", organism="Test Org",
            level=1, term_ids=None,
        )
        assert "coalesce(t.is_uninformative, '') <> 'true'" not in cypher

    def test_match_stage_appends_filter_when_informative_only(self):
        """Spec § per-builder table: shared helper appends
        `AND ($informative_only = false OR coalesce(t.is_uninformative, '') <> 'true')`
        before the size_filter WITH (term-level filter must apply before
        size collapse)."""
        from multiomics_explorer.kg.queries_lib import (
            _genes_by_ontology_match_stage,
        )
        cypher, _ = _genes_by_ontology_match_stage(
            ontology="go_bp", organism="Test Org",
            level=1, term_ids=None, informative_only=True,
        )
        assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_match_stage_filter_before_size_collapse(self):
        """Filter must apply BEFORE the `WITH t, collect(DISTINCT g) AS term_genes`
        size-collapse stage (otherwise it would filter on collapsed nodes)."""
        from multiomics_explorer.kg.queries_lib import (
            _genes_by_ontology_match_stage,
        )
        cypher, _ = _genes_by_ontology_match_stage(
            ontology="go_bp", organism="Test Org",
            level=1, term_ids=None, informative_only=True,
        )
        idx_filter = cypher.find("coalesce(t.is_uninformative, '') <> 'true'")
        idx_collapse = cypher.find("collect(DISTINCT g) AS term_genes")
        assert idx_filter != -1 and idx_collapse != -1
        assert idx_filter < idx_collapse

    # ---- detail: inherits filter, adds is_informative row column ------------
    def test_detail_default_is_informative_in_return(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="go_bp", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
        )
        assert "is_informative" in cypher
        assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_detail_default_omits_filter(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="go_bp", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
        )
        # Only the RETURN-side coalesce appears once; no WHERE-side filter.
        assert cypher.count("coalesce(t.is_uninformative, '') <> 'true'") == 1

    def test_detail_threads_informative_only(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_detail,
        )
        cypher, _ = build_genes_by_ontology_detail(
            ontology="go_bp", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
            informative_only=True,
        )
        # Now we expect ≥2 — once in WHERE filter, once in RETURN coalesce.
        assert cypher.count("coalesce(t.is_uninformative, '') <> 'true'") >= 2

    # ---- per_term: inherits filter, adds is_informative row column ----------
    def test_per_term_default_is_informative_in_return(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, _ = build_genes_by_ontology_per_term(
            ontology="go_bp", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
        )
        assert "is_informative" in cypher

    def test_per_term_threads_informative_only(self):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_term,
        )
        cypher, _ = build_genes_by_ontology_per_term(
            ontology="go_bp", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
            informative_only=True,
        )
        assert cypher.count("coalesce(t.is_uninformative, '') <> 'true'") >= 2

    # ---- per_gene: inherits filter, NO row column ---------------------------
    def test_per_gene_does_not_emit_is_informative_column(self):
        """Per-gene rows are per gene, not per term — `is_informative` is
        a per-term flag, so the row column does NOT belong here."""
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_gene,
        )
        cypher, _ = build_genes_by_ontology_per_gene(
            ontology="go_bp", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
        )
        assert "is_informative" not in cypher

    def test_per_gene_threads_informative_only_filter(self):
        """Filter still threads through (via shared helper) even though no
        row column — narrows which terms count toward this gene."""
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_ontology_per_gene,
        )
        cypher, _ = build_genes_by_ontology_per_gene(
            ontology="go_bp", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
            informative_only=True,
        )
        assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher


class TestBuildOntologyLandscapeF1Surface:
    """ontology_landscape: informative_only filter, default-on (True).

    Spec decision 3: ontology_landscape opts OUT (default True), opt-in via
    informative_only=False.
    No row-level `is_informative` (landscape is aggregated per ontology x level).
    """

    def test_default_filters_uninformative_terms(self):
        """Default `informative_only=True` ⇒ filter present in WHERE."""
        cypher, _ = build_ontology_landscape(
            ontology="cyanorak_role", organism_name="Prochlorococcus MED4",
        )
        assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_opt_out_omits_filter(self):
        cypher, _ = build_ontology_landscape(
            ontology="cyanorak_role", organism_name="Prochlorococcus MED4",
            informative_only=False,
        )
        assert "coalesce(t.is_uninformative, '') <> 'true'" not in cypher

    def test_no_is_informative_row_column(self):
        """ontology_landscape returns aggregated stats — no per-term rows.
        is_informative does NOT appear in RETURN."""
        cypher, _ = build_ontology_landscape(
            ontology="cyanorak_role", organism_name="Prochlorococcus MED4",
        )
        assert " AS is_informative" not in cypher


# ===========================================================================
# A3 — Enrichment defaults: pathway_enrichment + cluster_enrichment thread
# `informative_only` through to genes_by_ontology (frozen spec 2026-05-04).
# ===========================================================================
# The query builders themselves are unchanged for A3 — the existing
# build_genes_by_ontology_* helpers already support `informative_only` (covered
# by TestBuildGenesByOntologyF1Surface above). These tests pin the api-layer
# threading: when api.pathway_enrichment / api.cluster_enrichment invoke
# genes_by_ontology, the `informative_only` kwarg must flow through verbatim,
# defaulting to True per spec.


class TestPathwayEnrichmentBuilderInformativeOnly:
    """api.pathway_enrichment threads `informative_only` to genes_by_ontology.

    The query-builder layer is untouched (genes_by_ontology builders already
    accept the param via TestBuildGenesByOntologyF1Surface). These mock-based
    tests pin the orchestration: every internal genes_by_ontology call must
    receive the caller's `informative_only` value.
    """

    @staticmethod
    def _stub_de_result(rows=()):
        return {
            "organism_name": "MED4",
            "results": list(rows),
            "not_found": [], "not_matched": [], "no_expression": [],
        }

    @staticmethod
    def _stub_gbo_result(rows=()):
        return {
            "ontology": "cyanorak_role", "organism_name": "MED4",
            "results": list(rows),
            "not_found": [], "wrong_ontology": [],
            "wrong_level": [], "filtered_out": [],
        }

    def test_default_threads_informative_only_true(self, monkeypatch):
        """Spec § Default value: `informative_only: bool = True` on both tools.
        The internal genes_by_ontology call must receive informative_only=True
        when the caller passes nothing (the new default)."""
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f

        captured: dict = {}

        def _gbo(**kwargs):
            captured.update(kwargs)
            return self._stub_gbo_result()

        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(f, "genes_by_ontology", _gbo)

        pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
        )
        assert "informative_only" in captured, (
            "pathway_enrichment must thread informative_only to genes_by_ontology"
        )
        assert captured["informative_only"] is True, (
            "Default informative_only must be True (spec § Default value)"
        )

    def test_explicit_false_threads_through(self, monkeypatch):
        """Caller opt-out (`informative_only=False`) must reach genes_by_ontology
        unchanged."""
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f

        captured: dict = {}

        def _gbo(**kwargs):
            captured.update(kwargs)
            return self._stub_gbo_result()

        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(f, "genes_by_ontology", _gbo)

        pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            informative_only=False,
        )
        assert captured.get("informative_only") is False

    def test_explicit_true_threads_through(self, monkeypatch):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f

        captured: dict = {}

        def _gbo(**kwargs):
            captured.update(kwargs)
            return self._stub_gbo_result()

        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(f, "genes_by_ontology", _gbo)

        pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            informative_only=True,
        )
        assert captured.get("informative_only") is True


class TestClusterEnrichmentBuilderInformativeOnly:
    """api.cluster_enrichment threads `informative_only` to genes_by_ontology.

    Parallel to TestPathwayEnrichmentBuilderInformativeOnly — same param,
    same threading pattern. Builders themselves unchanged.
    """

    @staticmethod
    def _stub_inputs(gene_sets=None, not_found=(), not_matched=()):
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs
        if gene_sets is None:
            gene_sets = {"Cluster A": ["PMM0001", "PMM0002"]}
        return EnrichmentInputs(
            organism_name="MED4",
            gene_sets=gene_sets,
            background={"Cluster A": ["PMM0001", "PMM0002", "PMM0003"]},
            cluster_metadata={"Cluster A": {
                "cluster_id": "gc:1", "cluster_name": "Cluster A",
                "member_count": 2,
            }},
            not_found=list(not_found),
            not_matched=list(not_matched),
            no_expression=[],
            clusters_skipped=[],
            analysis_metadata={
                "analysis_id": "ca:test", "analysis_name": "Test",
                "cluster_method": "kmeans", "cluster_type": "diel_cycle",
                "omics_type": "transcriptomics",
                "treatment_type": ["light_dark"],
                "background_factors": [], "growth_phases": [],
                "experiment_ids": ["exp:1"],
            },
        )

    @staticmethod
    def _stub_gbo_result(rows=()):
        return {
            "ontology": "cyanorak_role", "organism_name": "MED4",
            "results": list(rows),
            "not_found": [], "wrong_ontology": [],
            "wrong_level": [], "filtered_out": [],
        }

    def test_default_threads_informative_only_true(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        captured: dict = {}

        def _gbo(**kwargs):
            captured.update(kwargs)
            return self._stub_gbo_result()

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(f, "genes_by_ontology", _gbo)

        cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            pvalue_cutoff=0.99,
        )
        assert "informative_only" in captured, (
            "cluster_enrichment must thread informative_only to genes_by_ontology"
        )
        assert captured["informative_only"] is True, (
            "Default informative_only must be True (spec § Default value)"
        )

    def test_explicit_false_threads_through(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        captured: dict = {}

        def _gbo(**kwargs):
            captured.update(kwargs)
            return self._stub_gbo_result()

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(f, "genes_by_ontology", _gbo)

        cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            informative_only=False, pvalue_cutoff=0.99,
        )
        assert captured.get("informative_only") is False

    def test_explicit_true_threads_through(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        captured: dict = {}

        def _gbo(**kwargs):
            captured.update(kwargs)
            return self._stub_gbo_result()

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(f, "genes_by_ontology", _gbo)

        cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            informative_only=True, pvalue_cutoff=0.99,
        )
        assert captured.get("informative_only") is True


# ===========================================================================
# Phase 1 — P0 pass-through plumbing (metabolites surface refresh)
# Spec: docs/tool-specs/2026-05-05-phase1-pass-through-plumbing.md
# 6 tools, all additive. Imports happen inside each test so collection
# still passes pre-impl.
# ===========================================================================


class TestBuildGeneOverviewPhase1Plumbing:
    """gene_overview detail: adds reaction_count + metabolite_count +
    transporter_count + evidence_sources per row. Path-existence subqueries
    derive evidence_sources (NOT a metabolite-level rollup) — see spec §6.1."""

    def test_compact_returns_reaction_count(self):
        cypher, _ = build_gene_overview(locus_tags=["PMM0001"])
        assert "coalesce(g.reaction_count, 0) AS reaction_count" in cypher

    def test_compact_returns_metabolite_count(self):
        """metabolite_count is reaction-OR-transport reachable, sourced from
        precomputed Gene.metabolite_count."""
        cypher, _ = build_gene_overview(locus_tags=["PMM0001"])
        assert "coalesce(g.metabolite_count, 0) AS metabolite_count" in cypher

    def test_compact_returns_transporter_count(self):
        """transporter_count surface alias of g.tcdb_family_count (spec §6.1)."""
        cypher, _ = build_gene_overview(locus_tags=["PMM0001"])
        assert "coalesce(g.tcdb_family_count, 0) AS transporter_count" in cypher

    def test_compact_returns_evidence_sources(self):
        """evidence_sources column present in RETURN."""
        cypher, _ = build_gene_overview(locus_tags=["PMM0001"])
        assert "evidence_sources" in cypher

    def test_evidence_sources_uses_path_existence(self):
        """Spec §6.1: path-existence subqueries (EXISTS { MATCH ... }) — NOT a
        rollup over m.evidence_sources. Without this, transport-only genes
        falsely tag as 'metabolism'."""
        cypher, _ = build_gene_overview(locus_tags=["PMM0001"])
        assert "EXISTS" in cypher
        # Both edges must be referenced for the path-existence subqueries
        assert "Gene_catalyzes_reaction" in cypher
        assert "Reaction_has_metabolite" in cypher
        assert "Gene_has_tcdb_family" in cypher
        assert "Tcdb_family_transports_metabolite" in cypher

    def test_evidence_sources_metabolomics_gated_by_measured(self):
        """metabolomics evidence requires reachable metabolite with
        measured_assay_count > 0 (path-existence + measurement gate)."""
        cypher, _ = build_gene_overview(locus_tags=["PMM0001"])
        assert "measured_assay_count" in cypher

    def test_verbose_still_has_chemistry_columns(self):
        """Verbose mode keeps all the new chemistry columns."""
        cypher, _ = build_gene_overview(locus_tags=["PMM0001"], verbose=True)
        assert "reaction_count" in cypher
        assert "metabolite_count" in cypher
        assert "transporter_count" in cypher
        assert "evidence_sources" in cypher


class TestBuildGeneOverviewSummaryPhase1Plumbing:
    """gene_overview_summary: adds has_chemistry envelope key."""

    def test_summary_returns_has_chemistry(self):
        cypher, _ = build_gene_overview_summary(locus_tags=["PMM0001"])
        assert "has_chemistry" in cypher


class TestBuildListPublicationsPhase1Plumbing:
    """list_publications detail: pass-through additions for measurement
    rollup fields on Publication node (spec §6.2)."""

    def test_compact_returns_metabolite_count(self):
        cypher, _ = build_list_publications()
        assert "coalesce(p.metabolite_count, 0) AS metabolite_count" in cypher

    def test_compact_returns_metabolite_assay_count(self):
        cypher, _ = build_list_publications()
        assert (
            "coalesce(p.metabolite_assay_count, 0) AS metabolite_assay_count"
            in cypher
        )

    def test_compact_returns_metabolite_compartments(self):
        """List sparse-default convention — coalesce to []."""
        cypher, _ = build_list_publications()
        assert (
            "coalesce(p.metabolite_compartments, []) AS metabolite_compartments"
            in cypher
        )

    def test_search_branch_also_has_metabolite_fields(self):
        """Both no-search and fulltext branches surface the new pass-throughs."""
        cypher, _ = build_list_publications(search_text="metabolite")
        assert "metabolite_count" in cypher
        assert "metabolite_assay_count" in cypher
        assert "metabolite_compartments" in cypher


class TestBuildListExperimentsPhase1Plumbing:
    """list_experiments detail: same shape as 6.2, pass-through from
    Experiment node properties (spec §6.3)."""

    def test_compact_returns_metabolite_count(self):
        cypher, _ = build_list_experiments()
        assert "coalesce(e.metabolite_count, 0) AS metabolite_count" in cypher

    def test_compact_returns_metabolite_assay_count(self):
        cypher, _ = build_list_experiments()
        assert (
            "coalesce(e.metabolite_assay_count, 0) AS metabolite_assay_count"
            in cypher
        )

    def test_compact_returns_metabolite_compartments(self):
        cypher, _ = build_list_experiments()
        assert (
            "coalesce(e.metabolite_compartments, []) AS metabolite_compartments"
            in cypher
        )

    def test_search_branch_also_has_metabolite_fields(self):
        cypher, _ = build_list_experiments(search_text="metabolite")
        assert "metabolite_count" in cypher
        assert "metabolite_assay_count" in cypher
        assert "metabolite_compartments" in cypher


class TestBuildListOrganismsPhase1Plumbing:
    """list_organisms detail: adds measured_metabolite_count per row.
    Summary: adds by_measurement_capability binary envelope rollup
    (spec §6.4)."""

    def test_detail_returns_measured_metabolite_count(self):
        cypher, _ = build_list_organisms()
        assert (
            "coalesce(o.measured_metabolite_count, 0) AS measured_metabolite_count"
            in cypher
        )

    def test_summary_returns_by_measurement_capability(self):
        cypher, _ = build_list_organisms_summary()
        assert "by_measurement_capability" in cypher

    def test_summary_capability_uses_binary_buckets(self):
        """Spec §6.4: binary 2-bucket count {has_metabolomics, no_metabolomics}.
        Summary builder must reference both bucket names."""
        cypher, _ = build_list_organisms_summary()
        assert "has_metabolomics" in cypher
        assert "no_metabolomics" in cypher

    def test_summary_capability_thresholds_on_measured_count(self):
        """Both buckets gate on measured_metabolite_count > 0 / = 0."""
        cypher, _ = build_list_organisms_summary()
        # Either form is acceptable; both must reference the prop.
        assert "measured_metabolite_count" in cypher


class TestBuildListMetabolitesPhase1Plumbing:
    """list_metabolites detail: pass-through additions for 4 measurement
    fields. Summary: adds by_measurement_coverage envelope (spec §6.6)."""

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import build_list_metabolites
        return build_list_metabolites(**kwargs)

    def _build_summary(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_list_metabolites_summary,
        )
        return build_list_metabolites_summary(**kwargs)

    def test_detail_returns_measured_assay_count(self):
        cypher, _ = self._build()
        assert (
            "coalesce(m.measured_assay_count, 0) AS measured_assay_count"
            in cypher
        )

    def test_detail_returns_measured_paper_count(self):
        cypher, _ = self._build()
        assert (
            "coalesce(m.measured_paper_count, 0) AS measured_paper_count"
            in cypher
        )

    def test_detail_returns_measured_organisms(self):
        """Sparse-default convention — coalesce to []."""
        cypher, _ = self._build()
        assert (
            "coalesce(m.measured_organisms, []) AS measured_organisms"
            in cypher
        )

    def test_detail_returns_measured_compartments(self):
        """KG-MET-016 closed; populated on all 107 measured metabolites,
        defaults to [] on the 3111 unmeasured (spec §6.6)."""
        cypher, _ = self._build()
        assert (
            "coalesce(m.measured_compartments, []) AS measured_compartments"
            in cypher
        )

    def test_search_branch_also_has_measurement_fields(self):
        """Search variant of detail builder threads the 4 measurement
        fields just like the no-search branch."""
        cypher, _ = self._build(search_text="glucose")
        assert "measured_assay_count" in cypher
        assert "measured_paper_count" in cypher
        assert "measured_organisms" in cypher
        assert "measured_compartments" in cypher

    def test_summary_returns_by_measurement_coverage(self):
        cypher, _ = self._build_summary()
        assert "by_measurement_coverage" in cypher

    def test_summary_coverage_has_paper_count_subkey(self):
        """Spec §6.6: by_measurement_coverage envelope = {by_paper_count, by_compartment}."""
        cypher, _ = self._build_summary()
        # The Cypher must surface both sub-rollup keys somewhere.
        assert "by_paper_count" in cypher

    def test_summary_coverage_has_compartment_subkey(self):
        cypher, _ = self._build_summary()
        # by_compartment from the measurement rollup (distinct from any DM
        # by_compartment elsewhere in the codebase — list_metabolites doesn't
        # carry DM rollups). The literal substring must appear.
        assert "by_compartment" in cypher


class TestBuildListOmicsTypes:
    """New filter_values branch: omics_type. Returns canonical OMICS_TYPE
    enum incl. METABOLOMICS (spec §6.5)."""

    def test_builder_function_exists(self):
        """build_list_omics_types must be importable from queries_lib."""
        from multiomics_explorer.kg.queries_lib import build_list_omics_types
        assert callable(build_list_omics_types)

    def test_returns_value_and_count_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_omics_types
        cypher, params = build_list_omics_types()
        # Conventional value/count return shape (matches sibling builders).
        assert "value" in cypher
        assert "count" in cypher
        assert params == {}

    def test_sources_from_experiment(self):
        """omics_type counts come from Experiment.omics_type."""
        from multiomics_explorer.kg.queries_lib import build_list_omics_types
        cypher, _ = build_list_omics_types()
        assert "Experiment" in cypher
        assert "omics_type" in cypher


class TestBuildListEvidenceSources:
    """New filter_values branch: evidence_source. Returns metabolism /
    transport / metabolomics with counts (spec §6.5)."""

    def test_builder_function_exists(self):
        from multiomics_explorer.kg.queries_lib import (
            build_list_evidence_sources,
        )
        assert callable(build_list_evidence_sources)

    def test_returns_value_and_count_columns(self):
        from multiomics_explorer.kg.queries_lib import (
            build_list_evidence_sources,
        )
        cypher, params = build_list_evidence_sources()
        assert "value" in cypher
        assert "count" in cypher
        assert params == {}

    def test_sources_from_metabolite_evidence_sources(self):
        """Counts derive from Metabolite.evidence_sources array."""
        from multiomics_explorer.kg.queries_lib import (
            build_list_evidence_sources,
        )
        cypher, _ = build_list_evidence_sources()
        assert "Metabolite" in cypher
        assert "evidence_sources" in cypher


# ===========================================================================
# Phase 2 — Cross-cutting renames + filter additions (frozen spec
# 2026-05-05-phase2-cross-cutting-renames.md). Stage 1 RED — failing tests.
# ===========================================================================
# 4 items:
#   1. list_metabolites: rename `search` Python kwarg → `search_text`
#      (Cypher param `$search` stays — internal fulltext-index arg).
#   2. list_metabolites + metabolites_by_gene: rename envelope
#      `top_pathways` → `top_metabolite_pathways`; per-element keys
#      `pathway_id`/`pathway_name` → `metabolite_pathway_id`/
#      `metabolite_pathway_name`. Other element keys unchanged.
#   3. list_metabolites + genes_by_metabolite + metabolites_by_gene:
#      add `exclude_metabolite_ids: list[str] | None = None` filter.
#      Cypher fragment: `(NOT (m.id IN $exclude_metabolite_ids))` —
#      parens are LOAD-BEARING (CyVer false-positive on unparenthesized
#      form when combined with another `IN` clause; spec §6.3 verified
#      against live KG 2026-05-05).
#   4. differential_expression_by_gene: add `direction='both'` branch
#      emitting `r.expression_status IN ['significant_up',
#      'significant_down']`.
# ===========================================================================


# --- Item 1 — search_text rename on list_metabolites detail builder ---


class TestBuildListMetabolitesPhase2SearchText:
    """Phase 2 Item 1 — `search` Python kwarg renames to `search_text`.

    The Cypher param name `$search` (passed to
    `db.index.fulltext.queryNodes('metaboliteFullText', $search)`) is
    internal and stays unchanged — only the Python kwarg renames.
    """

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import build_list_metabolites
        return build_list_metabolites(**kwargs)

    def test_search_text_param_threads(self):
        """Builder accepts `search_text=` kwarg and produces fulltext Cypher."""
        cypher, params = self._build(search_text="glucose")
        # Fulltext-index entrypoint preserved
        assert "metaboliteFullText" in cypher
        assert "YIELD node AS m, score" in cypher
        # Internal Cypher param name `$search` stays unchanged
        assert "$search" in cypher
        # Param value flows under the same Cypher key
        assert params["search"] == "glucose"

    def test_search_text_kwarg_only(self):
        """The old `search=` kwarg is gone — TypeError on unexpected kwarg."""
        with pytest.raises(TypeError):
            self._build(search="glucose")


class TestBuildListMetabolitesSummaryPhase2SearchText:
    """Phase 2 Item 1 — same rename on the summary builder."""

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_list_metabolites_summary,
        )
        return build_list_metabolites_summary(**kwargs)

    def test_search_text_param_threads(self):
        cypher, params = self._build(search_text="glucose")
        assert "metaboliteFullText" in cypher
        assert "$search" in cypher
        assert params["search"] == "glucose"


# --- Item 2 — top_metabolite_pathways rename ---


class TestBuildListMetabolitesSummaryPhase2TopMetabolitePathways:
    """Phase 2 Item 2 — RETURN aliases rename for list_metabolites summary.

    Spec §6.2: rename envelope key `top_pathways` →
    `top_metabolite_pathways`; rename per-element keys `pathway_id` /
    `pathway_name` → `metabolite_pathway_id` / `metabolite_pathway_name`.
    Other element keys (`count`) unchanged.
    """

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_list_metabolites_summary,
        )
        return build_list_metabolites_summary(**kwargs)

    def test_top_metabolite_pathways_alias(self):
        """RETURN aliases use the renamed envelope key + element keys."""
        cypher, _ = self._build()
        assert "top_metabolite_pathways" in cypher
        assert "metabolite_pathway_id" in cypher
        assert "metabolite_pathway_name" in cypher

    def test_old_aliases_absent(self):
        """Old `top_pathways` envelope alias and `pathway_id`/`pathway_name`
        per-element aliases must not appear in the renamed Cypher."""
        cypher, _ = self._build()
        # Pin the absence of the old element-key aliases (`AS pathway_id`,
        # `AS pathway_name`). A bare `pathway_id` substring would over-match
        # legitimate property reads on the metabolite (e.g. `m.pathway_ids`).
        assert "AS pathway_id" not in cypher
        assert "AS pathway_name" not in cypher
        # Old envelope-list alias absent.
        assert "AS top_pathways" not in cypher

    def test_top_metabolite_pathways_alias_with_search(self):
        """Search variant of the summary builder also emits the renamed
        aliases (search and non-search variants must agree per spec §6.2
        files-touched table)."""
        cypher, _ = self._build(search_text="glucose")
        assert "top_metabolite_pathways" in cypher
        assert "metabolite_pathway_id" in cypher
        assert "metabolite_pathway_name" in cypher


class TestBuildMetabolitesByGeneSummaryPhase2TopMetabolitePathways:
    """Phase 2 Item 2 — same rename for metabolites_by_gene summary."""

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_metabolites_by_gene_summary,
        )
        kwargs.setdefault("locus_tags", self._LOCUS)
        kwargs.setdefault("organism", self._ORG)
        return build_metabolites_by_gene_summary(**kwargs)

    def test_top_metabolite_pathways_alias(self):
        cypher, _ = self._build()
        assert "top_metabolite_pathways" in cypher
        assert "metabolite_pathway_id" in cypher
        assert "metabolite_pathway_name" in cypher

    def test_old_aliases_absent(self):
        cypher, _ = self._build()
        assert "AS pathway_id" not in cypher
        assert "AS pathway_name" not in cypher
        assert "AS top_pathways" not in cypher


# --- Item 3 — exclude_metabolite_ids filter (3 tools, 5 WHERE helpers) ---


class TestBuildListMetabolitesPhase2ExcludeMetaboliteIds:
    """Phase 2 Item 3 — exclude_metabolite_ids filter on detail builder.

    Cypher pattern: `(NOT (m.id IN $exclude_metabolite_ids))`. Parens
    are LOAD-BEARING per spec §6.3 (CyVer false-positive on
    unparenthesized form when combined with another `IN` clause).
    """

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import build_list_metabolites
        return build_list_metabolites(**kwargs)

    def test_exclude_metabolite_ids_filter(self):
        cypher, params = self._build(
            exclude_metabolite_ids=[
                "kegg.compound:C00002", "kegg.compound:C00008",
            ]
        )
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert params["exclude_metabolite_ids"] == [
            "kegg.compound:C00002", "kegg.compound:C00008",
        ]

    def test_exclude_combined_with_include(self):
        """Both `metabolite_ids` (include) and `exclude_metabolite_ids`
        (exclude) clauses appear AND-joined per set-difference semantics."""
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00031"],
            exclude_metabolite_ids=["kegg.compound:C00002"],
        )
        assert "m.id IN $metabolite_ids" in cypher
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert " AND " in cypher
        assert params["metabolite_ids"] == ["kegg.compound:C00031"]
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_exclude_none_no_filter(self):
        """Default (no exclude) produces no `exclude_metabolite_ids` clause."""
        cypher, params = self._build()
        assert "exclude_metabolite_ids" not in cypher
        assert "exclude_metabolite_ids" not in params

    def test_exclude_empty_list_no_filter(self):
        """Empty list is treated as None (no-op) per spec §6.3 truthy check."""
        cypher, params = self._build(exclude_metabolite_ids=[])
        assert "exclude_metabolite_ids" not in cypher
        assert "exclude_metabolite_ids" not in params


class TestBuildListMetabolitesSummaryPhase2ExcludeMetaboliteIds:
    """Phase 2 Item 3 — same filter on the summary builder."""

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_list_metabolites_summary,
        )
        return build_list_metabolites_summary(**kwargs)

    def test_exclude_metabolite_ids_filter(self):
        cypher, params = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_exclude_combined_with_include(self):
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00031"],
            exclude_metabolite_ids=["kegg.compound:C00002"],
        )
        assert "m.id IN $metabolite_ids" in cypher
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert " AND " in cypher


class TestBuildGenesByMetaboliteMetabolismPhase2ExcludeMetaboliteIds:
    """Phase 2 Item 3 — exclude on the metabolism arm WHERE helper of
    genes_by_metabolite. Per-arm scope: exclude applies on BOTH arms."""

    _METS = ["kegg.compound:C00086"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_metabolite_metabolism,
        )
        kwargs.setdefault("metabolite_ids", self._METS)
        kwargs.setdefault("organism", self._ORG)
        return build_genes_by_metabolite_metabolism(**kwargs)

    def test_exclude_metabolite_ids_filter(self):
        cypher, params = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_exclude_combined_with_include(self):
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00086", "kegg.compound:C00031"],
            exclude_metabolite_ids=["kegg.compound:C00002"],
        )
        assert "m.id IN $metabolite_ids" in cypher
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher


class TestBuildGenesByMetaboliteTransportPhase2ExcludeMetaboliteIds:
    """Phase 2 Item 3 — exclude on the transport arm WHERE helper."""

    _METS = ["kegg.compound:C00086"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_metabolite_transport,
        )
        kwargs.setdefault("metabolite_ids", self._METS)
        kwargs.setdefault("organism", self._ORG)
        return build_genes_by_metabolite_transport(**kwargs)

    def test_exclude_metabolite_ids_filter(self):
        cypher, params = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_exclude_combined_with_include(self):
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00086"],
            exclude_metabolite_ids=["kegg.compound:C00002"],
        )
        assert "m.id IN $metabolite_ids" in cypher
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher


class TestBuildGenesByMetaboliteSummaryPhase2ExcludeMetaboliteIds:
    """Phase 2 Item 3 — exclude on the summary (UNION) builder. The exclude
    clause must appear (in both UNION arms — verified via param presence)."""

    _METS = ["kegg.compound:C00086"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_genes_by_metabolite_summary,
        )
        kwargs.setdefault("metabolite_ids", self._METS)
        kwargs.setdefault("organism", self._ORG)
        return build_genes_by_metabolite_summary(**kwargs)

    def test_exclude_metabolite_ids_filter(self):
        cypher, params = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_exclude_appears_in_both_union_arms(self):
        """Per-arm scope: exclude applies on BOTH metabolism + transport arms.
        Since the summary builder UNIONs both, the exclude clause should
        appear at least twice in the generated Cypher (once per arm)."""
        cypher, _ = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert (
            cypher.count("(NOT (m.id IN $exclude_metabolite_ids))") >= 2
        )


class TestBuildMetabolitesByGeneMetabolismPhase2ExcludeMetaboliteIds:
    """Phase 2 Item 3 — exclude on the metabolism arm of metabolites_by_gene."""

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_metabolites_by_gene_metabolism,
        )
        kwargs.setdefault("locus_tags", self._LOCUS)
        kwargs.setdefault("organism", self._ORG)
        return build_metabolites_by_gene_metabolism(**kwargs)

    def test_exclude_metabolite_ids_filter(self):
        cypher, params = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_exclude_combined_with_include(self):
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00086"],
            exclude_metabolite_ids=["kegg.compound:C00002"],
        )
        assert "m.id IN $metabolite_ids" in cypher
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher


class TestBuildMetabolitesByGeneTransportPhase2ExcludeMetaboliteIds:
    """Phase 2 Item 3 — exclude on the transport arm of metabolites_by_gene."""

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_metabolites_by_gene_transport,
        )
        kwargs.setdefault("locus_tags", self._LOCUS)
        kwargs.setdefault("organism", self._ORG)
        return build_metabolites_by_gene_transport(**kwargs)

    def test_exclude_metabolite_ids_filter(self):
        cypher, params = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_exclude_combined_with_include(self):
        cypher, params = self._build(
            metabolite_ids=["kegg.compound:C00086"],
            exclude_metabolite_ids=["kegg.compound:C00002"],
        )
        assert "m.id IN $metabolite_ids" in cypher
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher


class TestBuildMetabolitesByGeneSummaryPhase2ExcludeMetaboliteIds:
    """Phase 2 Item 3 — exclude on the summary builder of metabolites_by_gene
    (UNION across both arms)."""

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    def _build(self, **kwargs):
        from multiomics_explorer.kg.queries_lib import (
            build_metabolites_by_gene_summary,
        )
        kwargs.setdefault("locus_tags", self._LOCUS)
        kwargs.setdefault("organism", self._ORG)
        return build_metabolites_by_gene_summary(**kwargs)

    def test_exclude_metabolite_ids_filter(self):
        cypher, params = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert "(NOT (m.id IN $exclude_metabolite_ids))" in cypher
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_exclude_appears_in_both_union_arms(self):
        cypher, _ = self._build(
            exclude_metabolite_ids=["kegg.compound:C00002"]
        )
        assert (
            cypher.count("(NOT (m.id IN $exclude_metabolite_ids))") >= 2
        )


# --- Item 4 — direction='both' branch on differential_expression_by_gene ---


class TestBuildDifferentialExpressionByGenePhase2DirectionBoth:
    """Phase 2 Item 4 — `direction='both'` emits IN-list Cypher.

    Spec §6.4: `r.expression_status IN ['significant_up',
    'significant_down']` — explicit positive form (robust to future
    status-vocabulary additions, vs. `<> 'not_significant'`).
    Functionally equivalent to `direction=None, significant_only=True`
    on the current 3-status universe (verified live KG 2026-05-05:
    51169 rows in both forms).
    """

    def test_direction_both_filter(self):
        cypher, _ = build_differential_expression_by_gene(direction="both")
        assert (
            "r.expression_status IN ['significant_up', 'significant_down']"
            in cypher
        )

    def test_direction_both_no_single_status_clause(self):
        """direction='both' must NOT emit a single-status equality clause
        (= 'significant_up' or = 'significant_down') — only the IN-list."""
        cypher, _ = build_differential_expression_by_gene(direction="both")
        # The new branch supersedes the up/down branches when
        # direction='both' — neither single-status clause should appear.
        assert "r.expression_status = 'significant_up'" not in cypher
        assert "r.expression_status = 'significant_down'" not in cypher

    def test_direction_up_unchanged(self):
        """Existing direction='up' branch is unchanged."""
        cypher, _ = build_differential_expression_by_gene(direction="up")
        assert "r.expression_status = 'significant_up'" in cypher
        assert (
            "r.expression_status IN ['significant_up', 'significant_down']"
            not in cypher
        )

    def test_direction_down_unchanged(self):
        """Existing direction='down' branch is unchanged."""
        cypher, _ = build_differential_expression_by_gene(direction="down")
        assert "r.expression_status = 'significant_down'" in cypher
        assert (
            "r.expression_status IN ['significant_up', 'significant_down']"
            not in cypher
        )


# ---------------------------------------------------------------------------
# list_metabolite_assays — Phase 5 (RED stage; impl lands in GREEN)
# Plan: docs/superpowers/plans/2026-05-06-list-metabolite-assays.md
# Tasks 1, 3, 5
# ---------------------------------------------------------------------------


class TestListMetaboliteAssaysWhere:
    """Tests for the shared WHERE-clause helper (mirrors _list_derived_metrics_where)."""

    def test_no_filters_returns_empty(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where()
        assert conditions == []
        assert params == {}

    def test_organism_space_split_contains(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(organism="MIT9301")
        assert len(conditions) == 1
        assert "ALL(word IN split(toLower($organism), ' ')" in conditions[0]
        assert "toLower(a.organism_name) CONTAINS word" in conditions[0]
        assert params == {"organism": "MIT9301"}

    def test_metric_types_list(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            metric_types=["cellular_concentration", "extracellular_concentration"])
        assert conditions == ["a.metric_type IN $metric_types"]
        assert params == {"metric_types": ["cellular_concentration", "extracellular_concentration"]}

    def test_value_kind_numeric(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(value_kind="numeric")
        assert conditions == ["a.value_kind = $value_kind"]
        assert params == {"value_kind": "numeric"}

    def test_value_kind_boolean(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(value_kind="boolean")
        assert conditions == ["a.value_kind = $value_kind"]
        assert params == {"value_kind": "boolean"}

    def test_compartment(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(compartment="whole_cell")
        assert conditions == ["a.compartment = $compartment"]
        assert params == {"compartment": "whole_cell"}

    def test_treatment_type_any_lowered(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(treatment_type=["Carbon", "PHOSPHORUS"])
        assert len(conditions) == 1
        assert "ANY(t IN coalesce(a.treatment_type, [])" in conditions[0]
        assert "toLower(t) IN $treatment_types_lower" in conditions[0]
        assert params == {"treatment_types_lower": ["carbon", "phosphorus"]}

    def test_background_factors_any_lowered_null_safe(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(background_factors=["Axenic"])
        assert len(conditions) == 1
        assert "ANY(bf IN coalesce(a.background_factors, [])" in conditions[0]
        assert params == {"background_factors_lower": ["axenic"]}

    def test_growth_phases_any_lowered(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(growth_phases=["Exponential"])
        assert len(conditions) == 1
        assert "ANY(gp IN coalesce(a.growth_phases, [])" in conditions[0]
        assert params == {"growth_phases_lower": ["exponential"]}

    def test_publication_doi_list(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            publication_doi=["10.1073/pnas.2213271120", "10.1128/msystems.01261-22"])
        assert conditions == ["a.publication_doi IN $publication_doi"]
        assert params == {
            "publication_doi": ["10.1073/pnas.2213271120", "10.1128/msystems.01261-22"]}

    def test_experiment_ids_list(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(experiment_ids=["exp_1"])
        assert conditions == ["a.experiment_id IN $experiment_ids"]
        assert params == {"experiment_ids": ["exp_1"]}

    def test_assay_ids_list(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            assay_ids=["metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration"])
        assert conditions == ["a.id IN $assay_ids"]
        assert "assay_ids" in params

    def test_metabolite_ids_uses_exists_clause(self):
        """metabolite_ids filter traverses both arms via EXISTS, not IN-list on a.*."""
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            metabolite_ids=["kegg.compound:C00074"])
        assert len(conditions) == 1
        assert "EXISTS {" in conditions[0]
        assert "Assay_quantifies_metabolite" in conditions[0]
        assert "Assay_flags_metabolite" in conditions[0]
        assert "m.id IN $metabolite_ids" in conditions[0]
        assert params == {"metabolite_ids": ["kegg.compound:C00074"]}

    def test_exclude_metabolite_ids_uses_not_exists(self):
        """exclude_metabolite_ids is set-difference on the same EXISTS shape."""
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            exclude_metabolite_ids=["kegg.compound:C00031"])
        assert len(conditions) == 1
        assert "NOT EXISTS {" in conditions[0]
        assert "m.id IN $exclude_metabolite_ids" in conditions[0]
        assert params == {"exclude_metabolite_ids": ["kegg.compound:C00031"]}

    def test_rankable_true_coerces_to_string(self):
        """Phase 5 D4: API takes bool, Cypher compares to string 'true'."""
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(rankable=True)
        assert conditions == ["a.rankable = $rankable_str"]
        assert params == {"rankable_str": "true"}

    def test_rankable_false_coerces_to_string(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(rankable=False)
        assert conditions == ["a.rankable = $rankable_str"]
        assert params == {"rankable_str": "false"}

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            organism="MIT9301", value_kind="boolean", rankable=False)
        assert len(conditions) == 3
        assert params.keys() == {"organism", "value_kind", "rankable_str"}


class TestBuildListMetaboliteAssaysSummary:
    """Tests for the summary-mode Cypher builder."""

    def test_no_filters_no_search(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, params = build_list_metabolite_assays_summary()
        assert "MATCH (a:MetaboliteAssay)" in cypher
        assert "CALL { MATCH (all_a:MetaboliteAssay) RETURN count(all_a) AS total_entries }" in cypher
        assert "OPTIONAL MATCH (a)-[r:Assay_quantifies_metabolite]->(:Metabolite)" in cypher
        assert "[s IN collect(r.detection_status) WHERE s IS NOT NULL]" in cypher
        assert "apoc.coll.frequencies(orgs) AS by_organism" in cypher
        assert "apoc.coll.frequencies(vks) AS by_value_kind" in cypher
        assert "apoc.coll.frequencies(comps) AS by_compartment" in cypher
        assert "apoc.coll.frequencies(mts) AS top_metric_types" in cypher
        assert "apoc.coll.frequencies(tts) AS by_treatment_type" in cypher
        assert "apoc.coll.frequencies(bfs) AS by_background_factors" in cypher
        assert "apoc.coll.frequencies(gps) AS by_growth_phase" in cypher
        assert "apoc.coll.frequencies(all_det) AS by_detection_status" in cypher
        assert "sum(a.total_metabolite_count) AS metabolite_count_total" in cypher
        # Scope assertion: no user-filter WHERE block. (NULL-safe inner WHEREs
        # like `WHERE s IS NOT NULL` per parent §13.7 are mandated, so the
        # too-broad `assert "WHERE" not in cypher` would conflict with the
        # NULL-safety convention. Check the param-placeholders that
        # _list_metabolite_assays_where would inject — no filter ⇒ none.)
        assert "$organism" not in cypher
        assert "$value_kind" not in cypher
        assert "$compartment" not in cypher
        assert "$rankable_str" not in cypher
        assert "$metric_types" not in cypher
        assert params == {}

    def test_with_organism_adds_where(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, params = build_list_metabolite_assays_summary(organism="MIT9313")
        assert "WHERE ALL(word IN split(toLower($organism), ' ')" in cypher
        assert "toLower(a.organism_name) CONTAINS word" in cypher
        assert params == {"organism": "MIT9313"}

    def test_search_text_uses_fulltext_index(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, params = build_list_metabolite_assays_summary(search_text="chitosan")
        assert "CALL db.index.fulltext.queryNodes('metaboliteAssayFullText'" in cypher
        assert "YIELD node AS a, score" in cypher
        assert "max(score) AS score_max" in cypher
        assert "percentileDisc(score, 0.5) AS score_median" in cypher
        assert params == {"search_text": "chitosan"}

    def test_search_text_combined_with_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, params = build_list_metabolite_assays_summary(
            search_text="cellular concentration", value_kind="numeric")
        assert "metaboliteAssayFullText" in cypher
        assert "WHERE a.value_kind = $value_kind" in cypher
        assert params == {"search_text": "cellular concentration", "value_kind": "numeric"}

    def test_shares_where_clause_with_helper(self):
        """Filters from _list_metabolite_assays_where flow through unchanged."""
        from multiomics_explorer.kg.queries_lib import (
            build_list_metabolite_assays_summary,
            _list_metabolite_assays_where,
        )
        cypher, params = build_list_metabolite_assays_summary(
            organism="MIT9301", rankable=True, value_kind="numeric")
        helper_conds, helper_params = _list_metabolite_assays_where(
            organism="MIT9301", rankable=True, value_kind="numeric")
        for cond in helper_conds:
            assert cond in cypher
        assert params == helper_params

    def test_metabolite_count_total_summed(self):
        """metabolite_count_total is sum across matching assays (cumulative, not distinct)."""
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, _ = build_list_metabolite_assays_summary()
        assert "sum(a.total_metabolite_count) AS metabolite_count_total" in cypher


class TestBuildListMetaboliteAssays:
    """Tests for the detail-mode Cypher builder."""

    def test_no_filters_compact(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays()
        assert "MATCH (a:MetaboliteAssay)" in cypher
        # Compact RETURN columns
        assert "a.id AS assay_id" in cypher
        assert "a.name AS name" in cypher
        assert "a.metric_type AS metric_type" in cypher
        assert "a.value_kind AS value_kind" in cypher
        assert "(a.rankable = \"true\") AS rankable" in cypher  # bool coercion
        assert "a.unit AS unit" in cypher
        assert "a.field_description AS field_description" in cypher
        assert "a.organism_name AS organism_name" in cypher
        assert "a.experiment_id AS experiment_id" in cypher
        assert "a.publication_doi AS publication_doi" in cypher
        assert "a.compartment AS compartment" in cypher
        assert "a.omics_type AS omics_type" in cypher
        assert "coalesce(a.treatment_type, []) AS treatment_type" in cypher
        assert "coalesce(a.background_factors, []) AS background_factors" in cypher
        assert "coalesce(a.growth_phases, []) AS growth_phases" in cypher
        assert "a.total_metabolite_count AS total_metabolite_count" in cypher
        assert "a.aggregation_method AS aggregation_method" in cypher
        assert "a.preferred_id AS preferred_id" in cypher
        assert "a.value_min AS value_min" in cypher
        assert "a.value_q1 AS value_q1" in cypher
        assert "a.value_median AS value_median" in cypher
        assert "a.value_q3 AS value_q3" in cypher
        assert "a.value_max AS value_max" in cypher
        # timepoints rollup with sentinel-stripping
        assert (
            "[label IN collect(DISTINCT r.time_point) "
            "WHERE label IS NOT NULL AND label <> \"\" | label]"
        ) in cypher
        assert "AS timepoints" in cypher
        # detection_status_counts rollup
        assert "apoc.coll.frequencies(detection_statuses)" in cypher
        assert "AS detection_status_counts" in cypher
        # Verbose-only fields not present in compact
        assert "a.treatment AS treatment" not in cypher
        assert "a.light_condition AS light_condition" not in cypher
        # Sort key
        assert "ORDER BY a.organism_name ASC, a.value_kind ASC, a.id ASC" in cypher
        assert params == {}

    def test_verbose_adds_text_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, _ = build_list_metabolite_assays(verbose=True)
        assert "a.treatment AS treatment" in cypher
        assert "a.light_condition AS light_condition" in cypher
        assert "a.experimental_context AS experimental_context" in cypher

    def test_search_text_uses_fulltext_and_score(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(search_text="chitosan")
        assert "CALL db.index.fulltext.queryNodes('metaboliteAssayFullText'" in cypher
        assert "YIELD node AS a, score" in cypher
        assert "score AS score" in cypher
        # Score-DESC must be the leading sort key when searching
        assert "ORDER BY score DESC, a.organism_name ASC" in cypher
        assert params == {"search_text": "chitosan"}

    def test_limit_offset_clauses(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(limit=20, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params == {"limit": 20, "offset": 5}

    def test_limit_none_omits_clauses(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(limit=None, offset=0)
        assert "LIMIT" not in cypher
        assert "SKIP" not in cypher
        assert params == {}

    def test_filters_through_helper(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(
            organism="MIT9313", value_kind="numeric", rankable=True)
        assert "WHERE" in cypher
        assert "a.value_kind = $value_kind" in cypher
        assert "a.rankable = $rankable_str" in cypher
        assert params["value_kind"] == "numeric"
        assert params["rankable_str"] == "true"
        assert params["organism"] == "MIT9313"

    def test_rankable_returned_as_bool_via_string_compare(self):
        """Per Phase 5 D4: per-row rankable is bool, derived from string compare."""
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, _ = build_list_metabolite_assays()
        assert "(a.rankable = \"true\") AS rankable" in cypher

    def test_metabolite_ids_filter_appears(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(
            metabolite_ids=["kegg.compound:C00074"])
        assert "EXISTS {" in cypher
        assert "Assay_quantifies_metabolite|Assay_flags_metabolite" in cypher
        assert params == {"metabolite_ids": ["kegg.compound:C00074"]}


# ---------------------------------------------------------------------------
# Phase 5 metabolites-by-assay slice — 3 tools
# Tool 1: metabolites_by_quantifies_assay (numeric drill-down)
# Tool 2: metabolites_by_flags_assay (boolean drill-down)
# Tool 3: assays_by_metabolite (polymorphic reverse-lookup)
# ---------------------------------------------------------------------------
class TestMetabolitesByQuantifiesAssayWhere:
    """Unit tests for the shared WHERE-clause helper for metabolites_by_quantifies_assay."""

    def test_no_filters_returns_only_required(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where()
        assert conditions == []
        assert params == {}

    def test_organism_contains_lowercased(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(organism="MIT9313")
        assert any("toLower(a.organism_name) CONTAINS" in c for c in conditions)
        assert params == {"organism": "mit9313"}

    def test_metabolite_ids_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            metabolite_ids=["kegg.compound:C00074"])
        assert "m.id IN $metabolite_ids" in conditions
        assert params["metabolite_ids"] == ["kegg.compound:C00074"]

    def test_exclude_metabolite_ids_set_difference(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            exclude_metabolite_ids=["kegg.compound:C00002"])
        assert "NOT m.id IN $exclude_metabolite_ids" in conditions
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_value_min_strips_tested_absent_warning(self):
        # Sanity: builder must accept value_min and emit raw threshold.
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(value_min=0.01)
        assert "r.value >= $value_min" in conditions
        assert params["value_min"] == 0.01

    def test_value_max(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(value_max=10.0)
        assert "r.value <= $value_max" in conditions

    def test_detection_status_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            detection_status=["detected", "sporadic"])
        assert "r.detection_status IN $detection_status" in conditions
        assert params["detection_status"] == ["detected", "sporadic"]

    def test_metric_bucket_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            metric_bucket=["top_decile", "top_quartile"])
        assert "r.metric_bucket IN $metric_bucket" in conditions

    def test_metric_percentile_min_max(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            metric_percentile_min=10.0, metric_percentile_max=90.0)
        assert "r.metric_percentile >= $metric_percentile_min" in conditions
        assert "r.metric_percentile <= $metric_percentile_max" in conditions

    def test_rank_by_metric_max(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(rank_by_metric_max=10)
        assert "r.rank_by_metric <= $rank_by_metric_max" in conditions
        assert params["rank_by_metric_max"] == 10

    def test_timepoint_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(timepoint=["4 days", "6 days"])
        assert "r.time_point IN $timepoint" in conditions
        assert params["timepoint"] == ["4 days", "6 days"]

    def test_compartment_exact(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(compartment="whole_cell")
        assert "a.compartment = $compartment" in conditions

    def test_treatment_type_lowercased_overlap(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(treatment_type=["Light", "Dark"])
        assert any("ANY(t IN coalesce(a.treatment_type, [])" in c for c in conditions)
        assert any("toLower(t) IN $treatment_types_lower" in c for c in conditions)
        assert params["treatment_types_lower"] == ["light", "dark"]

    def test_publication_doi_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            publication_doi=["10.1073/pnas.2213271120"])
        assert "a.publication_doi IN $publication_doi" in conditions

    def test_experiment_ids_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(experiment_ids=["EXP_1"])
        assert "a.experiment_id IN $experiment_ids" in conditions


class TestBuildMetabolitesByQuantifiesAssayDiagnostics:
    """Unit tests for build_metabolites_by_quantifies_assay_diagnostics."""

    def test_returns_rankable_per_assay(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_diagnostics
        cypher, params = build_metabolites_by_quantifies_assay_diagnostics(
            assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"])
        assert "MATCH (a:MetaboliteAssay)" in cypher
        assert "a.id IN $assay_ids" in cypher
        assert "a.value_kind = 'numeric'" in cypher
        assert "(a.rankable = 'true') AS rankable" in cypher       # D4 string→bool
        assert "a.value_min" in cypher and "a.value_max" in cypher  # so api/ can echo full-DM range
        assert params["assay_ids"] == [
            "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"]

    def test_organism_filter_passes_through(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_diagnostics
        cypher, params = build_metabolites_by_quantifies_assay_diagnostics(
            assay_ids=["a1"], organism="MIT9313")
        assert "toLower(a.organism_name) CONTAINS" in cypher
        assert "mit9313" in str(params).lower()


class TestBuildMetabolitesByQuantifiesAssaySummary:
    """Unit tests for build_metabolites_by_quantifies_assay_summary (parent §12.2)."""

    def test_match_pattern(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_summary
        cypher, params = build_metabolites_by_quantifies_assay_summary(
            assay_ids=["a1"])
        assert "MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(m:Metabolite)" in cypher
        assert "a.id IN $assay_ids" in cypher

    def test_envelope_keys(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_summary
        cypher, _ = build_metabolites_by_quantifies_assay_summary(assay_ids=["a1"])
        for key in ("by_detection_status", "by_metric_bucket", "by_assay",
                    "by_compartment", "by_organism",
                    "filtered_value_min", "filtered_value_max", "total_matching"):
            assert key in cypher

    def test_detection_status_filter_passthrough(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_summary
        cypher, params = build_metabolites_by_quantifies_assay_summary(
            assay_ids=["a1"], detection_status=["detected", "sporadic"])
        assert "r.detection_status IN $detection_status" in cypher
        assert params["detection_status"] == ["detected", "sporadic"]

    def test_value_min_passthrough(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_summary
        cypher, params = build_metabolites_by_quantifies_assay_summary(
            assay_ids=["a1"], value_min=0.01)
        assert "r.value >= $value_min" in cypher


class TestBuildMetabolitesByQuantifiesAssay:
    """Unit tests for build_metabolites_by_quantifies_assay (detail, parent §12.2)."""

    def test_match_and_optional_experiment_join(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        assert "MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(m:Metabolite)" in cypher
        assert "OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)" in cypher

    def test_sentinel_coercions(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        # D3: empty-string / -1.0 / 0 → null
        assert "CASE WHEN r.time_point = '' THEN null ELSE r.time_point END AS timepoint" in cypher
        assert "CASE WHEN r.time_point_hours = -1.0 THEN null ELSE r.time_point_hours END" in cypher
        assert "CASE WHEN r.time_point_order = 0 THEN null ELSE r.time_point_order END" in cypher

    def test_growth_phase_lookup_guarded(self):
        # KG-MET-017: time_point_growth_phases[] is empty today; lookup must coalesce safely.
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        assert "size(coalesce(e.time_point_growth_phases, []))" in cypher
        assert "AS growth_phase" in cypher

    def test_order_by_rank(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        assert "ORDER BY r.rank_by_metric ASC" in cypher
        assert "m.id ASC" in cypher

    def test_verbose_adds_heavy_text(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher_default, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        cypher_verbose, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"], verbose=True)
        for f in ("a.name AS assay_name", "a.field_description AS field_description",
                  "a.experimental_context", "a.light_condition", "r.replicate_values"):
            assert f not in cypher_default
            assert f in cypher_verbose

    def test_limit_offset(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, params = build_metabolites_by_quantifies_assay(assay_ids=["a1"], limit=20, offset=5)
        assert "SKIP $offset LIMIT $limit" in cypher
        assert params["limit"] == 20 and params["offset"] == 5


class TestBuildMetabolitesByFlagsAssaySummary:
    """Unit tests for build_metabolites_by_flags_assay_summary (parent §12.3)."""

    def test_match_and_envelope(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay_summary
        cypher, params = build_metabolites_by_flags_assay_summary(assay_ids=["a1"])
        assert "MATCH (a:MetaboliteAssay)-[r:Assay_flags_metabolite]->(m:Metabolite)" in cypher
        assert "a.id IN $assay_ids" in cypher
        for key in ("by_value", "by_assay", "by_compartment", "by_organism", "total_matching"):
            assert key in cypher

    def test_no_detection_status_envelope(self):
        # Boolean arm has no detection_status; document via test.
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay_summary
        cypher, _ = build_metabolites_by_flags_assay_summary(assay_ids=["a1"])
        assert "by_detection_status" not in cypher

    def test_flag_value_filter_string_form(self):
        # D4: API coerces bool → string before passing to Cypher.
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay_summary
        cypher, params = build_metabolites_by_flags_assay_summary(assay_ids=["a1"], flag_value="true")
        assert "r.flag_value = $flag_value" in cypher
        assert params["flag_value"] == "true"


class TestBuildMetabolitesByFlagsAssay:
    """Unit tests for build_metabolites_by_flags_assay (detail, parent §12.3)."""

    def test_string_to_bool_coercion_in_return(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay
        cypher, _ = build_metabolites_by_flags_assay(assay_ids=["a1"])
        assert "(r.flag_value = 'true') AS flag_value" in cypher

    def test_order_by_flag_desc(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay
        cypher, _ = build_metabolites_by_flags_assay(assay_ids=["a1"])
        assert "ORDER BY r.flag_value DESC" in cypher
        assert "m.id ASC" in cypher

    def test_verbose_adds_minimal(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay
        cypher_def, _ = build_metabolites_by_flags_assay(assay_ids=["a1"])
        cypher_v, _ = build_metabolites_by_flags_assay(assay_ids=["a1"], verbose=True)
        for f in ("a.name AS assay_name", "a.field_description AS field_description"):
            assert f not in cypher_def
            assert f in cypher_v


class TestBuildAssaysByMetaboliteSummary:
    """Unit tests for build_assays_by_metabolite_summary (parent §12.4 UNION ALL)."""

    def test_union_all_with_distinct_rel_vars(self):
        # Parent §12.4 caveat: production builder MUST use UNION ALL with rq/rf rel-vars.
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite_summary
        cypher, _ = build_assays_by_metabolite_summary(metabolite_ids=["kegg.compound:C00074"])
        assert "UNION ALL" in cypher
        assert "[rq:Assay_quantifies_metabolite]" in cypher
        assert "[rf:Assay_flags_metabolite]" in cypher
        # Anti-pattern guard: the polymorphic merged form must NOT appear.
        assert "[r:Assay_quantifies_metabolite|Assay_flags_metabolite]" not in cypher

    def test_envelope_keys(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite_summary
        cypher, _ = build_assays_by_metabolite_summary(metabolite_ids=["kegg.compound:C00074"])
        for key in ("by_evidence_kind", "by_organism", "by_compartment", "by_assay",
                    "by_detection_status", "by_flag_value", "metabolites_matched",
                    "total_matching"):
            assert key in cypher

    def test_null_filter_on_collected_arrays(self):
        # Parent §13.7: collect() drops NULLs; explicit guard for cross-arm boundary.
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite_summary
        cypher, _ = build_assays_by_metabolite_summary(metabolite_ids=["kegg.compound:C00074"])
        assert "[d IN collect(det) WHERE d IS NOT NULL]" in cypher
        assert "[f IN collect(flag) WHERE f IS NOT NULL]" in cypher

    def test_evidence_kind_quantifies_only(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite_summary
        cypher, _ = build_assays_by_metabolite_summary(
            metabolite_ids=["kegg.compound:C00074"], evidence_kind="quantifies")
        # When quantifies-only, the flags branch MUST NOT contribute rows.
        # Implementation detail: builder either (a) emits only the quantifies branch, or
        # (b) emits both branches with a guard that empties the flags branch. Either is OK
        # so long as result-row evidence_kind is constant.
        assert "rq:Assay_quantifies_metabolite" in cypher


class TestBuildAssaysByMetabolite:
    """Unit tests for build_assays_by_metabolite (detail, parent §12.4 UNION ALL)."""

    def test_union_all_skeleton(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite
        cypher, _ = build_assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"])
        assert "UNION ALL" in cypher
        assert "[rq:Assay_quantifies_metabolite]" in cypher
        assert "[rf:Assay_flags_metabolite]" in cypher
        # Both branches MUST emit the same column list (UNION ALL constraint).
        # Cross-arm fields padded with explicit nulls per §6.2.
        assert "null AS flag_value" in cypher        # from quantifies branch
        assert "null AS value" in cypher              # from flags branch
        assert "null AS metric_bucket" in cypher      # from flags branch (rankable-only)
        assert "null AS detection_status" in cypher   # from flags branch
        assert "null AS timepoint" in cypher          # from flags branch
        assert "'quantifies' AS evidence_kind" in cypher
        assert "'flags' AS evidence_kind" in cypher

    def test_optional_match_experiment_only_in_quantifies_branch(self):
        # Quantifies branch needs e.time_point_growth_phases for growth_phase lookup.
        # Flags branch has no temporal fields; experiment join is unnecessary.
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite
        cypher, _ = build_assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"])
        assert "OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)" in cypher

    def test_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite
        cypher, _ = build_assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"])
        assert "ORDER BY metabolite_id ASC, evidence_kind DESC" in cypher
        assert "coalesce(timepoint_order, 999999) ASC" in cypher

    def test_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite
        cypher, params = build_assays_by_metabolite(
            metabolite_ids=["kegg.compound:C00074"], organism="MIT9313")
        assert params.get("organism") == "mit9313"
