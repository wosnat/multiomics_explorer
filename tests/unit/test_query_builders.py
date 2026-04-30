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
            "brite",
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
                         "cog_category", "cyanorak_role", "tigr_role"]:
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
        "brite",
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
