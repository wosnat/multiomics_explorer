"""Unit tests for query builder functions — no Neo4j needed.

Verifies Cypher structure and parameter correctness.
"""

import pytest

from multiomics_explorer.kg.queries_lib import (
    ONTOLOGY_CONFIG,
    build_gene_existence_check,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_gene_ontology_terms,
    build_gene_ontology_terms_summary,
    build_gene_overview,
    build_gene_overview_summary,
    build_genes_by_function,
    build_genes_by_function_summary,
    build_genes_by_ontology,
    build_genes_by_ontology_summary,
    build_gene_details,
    build_gene_details_summary,
    build_list_gene_categories,
    build_list_organisms,
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
    build_differential_expression_by_ortholog_summary_global,
    build_differential_expression_by_ortholog_top_groups,
    build_differential_expression_by_ortholog_top_experiments,
    build_differential_expression_by_ortholog_results,
    build_differential_expression_by_ortholog_membership_counts,
    build_differential_expression_by_ortholog_diagnostics,
    build_resolve_organism_for_organism,
    build_resolve_organism_for_locus_tags,
    build_resolve_organism_for_experiments,
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

    def test_returns_total_entries_and_total_matching(self):
        """RETURN clause includes both total_entries and total_matching."""
        cypher, _ = build_genes_by_function_summary(search_text="x")
        assert "total_entries" in cypher
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
        assert "not_found" in cypher
        assert params["locus_tags"] == ["PMM1428"]

    def test_not_found_logic(self):
        """Summary query detects not_found via OPTIONAL MATCH + CASE WHEN g IS NULL."""
        cypher, _ = build_gene_overview_summary(locus_tags=["PMM1428", "FAKE"])
        assert "OPTIONAL MATCH" in cypher
        assert "CASE WHEN g IS NULL" in cypher


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

    def test_combined_filters(self):
        """All three filters appear in WHERE."""
        cypher, params = build_gene_homologs_summary(
            locus_tags=["x"], source="eggnog", taxonomic_level="Bacteria",
            max_specificity_rank=3,
        )
        assert "og.source = $source" in cypher
        assert "og.taxonomic_level = $level" in cypher
        assert "og.specificity_rank <= $max_rank" in cypher


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

    def test_no_params(self):
        _, params = build_list_organisms()
        assert params == {}

    def test_ordered_by_genus_and_name(self):
        cypher, _ = build_list_organisms()
        assert "ORDER BY o.genus, o.preferred_name" in cypher


class TestOntologyConfig:
    def test_all_keys_present(self):
        assert set(ONTOLOGY_CONFIG.keys()) == {
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam",
        }

    def test_required_fields_present(self):
        for key, cfg in ONTOLOGY_CONFIG.items():
            assert "label" in cfg, f"{key} missing 'label'"
            assert "gene_rel" in cfg, f"{key} missing 'gene_rel'"
            assert "hierarchy_rels" in cfg, f"{key} missing 'hierarchy_rels'"
            assert "fulltext_index" in cfg, f"{key} missing 'fulltext_index'"

    def test_only_kegg_has_gene_connects_to_level(self):
        for key, cfg in ONTOLOGY_CONFIG.items():
            if key == "kegg":
                assert cfg.get("gene_connects_to_level") == "ko"
            else:
                assert "gene_connects_to_level" not in cfg, (
                    f"{key} should not have 'gene_connects_to_level'"
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


class TestBuildGenesByOntology:
    def test_go_bp_hierarchy_expansion(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"],
        )
        assert "Biological_process_is_a_biological_process|Biological_process_part_of_biological_process" in cypher
        assert "*0..15" in cypher
        assert "BiologicalProcess" in cypher

    def test_ec_hierarchy_expansion(self):
        cypher, _ = build_genes_by_ontology(
            ontology="ec", term_ids=["ec:1.-.-.-"],
        )
        assert "Ec_number_is_a_ec_number" in cypher
        assert "*0..15" in cypher

    def test_kegg_has_level_filter(self):
        cypher, _ = build_genes_by_ontology(
            ontology="kegg", term_ids=["kegg.category:09100"],
        )
        assert "Kegg_term_is_a_kegg_term" in cypher
        assert "*0..15" in cypher
        assert "descendant.level = 'ko'" in cypher

    def test_non_kegg_no_level_filter(self):
        for ontology in ["go_bp", "go_mf", "go_cc", "ec"]:
            cypher, _ = build_genes_by_ontology(
                ontology=ontology, term_ids=["test:001"],
            )
            assert "level" not in cypher, f"{ontology} should not have level filter"

    def test_organism_filter_in_where(self):
        cypher, params = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"], organism="MED4",
        )
        assert params["organism"] == "MED4"
        assert "toLower($organism)" in cypher

    def test_term_ids_passed_as_parameter(self):
        cypher, params = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260", "go:0006139"],
        )
        assert params["term_ids"] == ["go:0006260", "go:0006139"]
        assert "$term_ids" in cypher

    def test_returns_expected_columns(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"],
        )
        for col in ["locus_tag", "gene_name", "product", "organism_name"]:
            assert col in cypher

    def test_invalid_ontology_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_genes_by_ontology(ontology="bad", term_ids=["x"])

    def test_go_mf_hierarchy_expansion(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_mf", term_ids=["go:0003677"],
        )
        assert "MolecularFunction" in cypher
        assert "Molecular_function_is_a_molecular_function" in cypher

    def test_go_cc_hierarchy_expansion(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_cc", term_ids=["go:0016020"],
        )
        assert "CellularComponent" in cypher
        assert "Cellular_component_is_a_cellular_component" in cypher

    def test_flat_ontology_no_hierarchy_expansion(self):
        """Flat ontologies (empty hierarchy_rels) skip *0..15 traversal."""
        cypher, _ = build_genes_by_ontology(
            ontology="cog_category", term_ids=["cog.category:C"],
        )
        assert "*0..15" not in cypher
        assert "root AS descendant" in cypher
        assert "CogFunctionalCategory" in cypher
        assert "Gene_in_cog_category" in cypher

    def test_hierarchical_new_ontology(self):
        """CyanorakRole has hierarchy and should use *0..15 traversal."""
        cypher, _ = build_genes_by_ontology(
            ontology="cyanorak_role", term_ids=["cyanorak.role:F"],
        )
        assert "Cyanorak_role_is_a_cyanorak_role" in cypher
        assert "*0..15" in cypher

    def test_pfam_multi_label_root(self):
        """Pfam generates multi-label root match accepting both Pfam and PfamClan."""
        cypher, _ = build_genes_by_ontology(
            ontology="pfam", term_ids=["pfam:PF00712"],
        )
        assert "root:Pfam OR root:PfamClan" in cypher
        assert "Pfam_in_pfam_clan" in cypher
        assert "*0..15" in cypher
        assert "Gene_has_pfam" in cypher

    def test_non_pfam_single_label_root(self):
        """Non-pfam ontologies use single-label root match."""
        for ontology in ["go_bp", "go_mf", "go_cc", "ec", "kegg",
                         "cog_category", "cyanorak_role", "tigr_role"]:
            cypher, _ = build_genes_by_ontology(
                ontology=ontology, term_ids=["test:001"],
            )
            assert "OR root:" not in cypher, f"{ontology} should not have multi-label root"

    def test_verbose_false_no_gene_summary(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"], verbose=False,
        )
        assert "gene_summary" not in cypher
        assert "function_description" not in cypher
        assert "matched_terms" not in cypher

    def test_verbose_true_adds_columns(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"], verbose=True,
        )
        assert "gene_summary" in cypher
        assert "function_description" in cypher
        assert "matched_terms" in cypher

    def test_verbose_tid_survives_with_distinct(self):
        """UNWIND-based verbose query must carry tid through WITH DISTINCT."""
        cypher, _ = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"], verbose=True,
        )
        for line in cypher.split("\n"):
            if "WITH DISTINCT" in line and "descendant" in line:
                assert "tid" in line, f"tid dropped from scope: {line}"

    def test_limit_clause(self):
        cypher, params = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"], limit=10,
        )
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"],
        )
        assert "LIMIT" not in cypher

    def test_order_by_organism_then_locus(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"],
        )
        assert "ORDER BY g.organism_name, g.locus_tag" in cypher

    def test_gene_category_in_compact(self):
        cypher, _ = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"],
        )
        assert "gene_category" in cypher


class TestBuildGenesByOntologySummary:
    def test_returns_summary_keys(self):
        cypher, _ = build_genes_by_ontology_summary(
            ontology="go_bp", term_ids=["go:0006260"],
        )
        for key in ["total_matching", "by_organism", "by_category", "by_term"]:
            assert key in cypher

    def test_uses_apoc_frequencies(self):
        cypher, _ = build_genes_by_ontology_summary(
            ontology="go_bp", term_ids=["go:0006260"],
        )
        assert "apoc.coll.frequencies" in cypher

    def test_organism_filter(self):
        cypher, params = build_genes_by_ontology_summary(
            ontology="go_bp", term_ids=["go:0006260"], organism="MED4",
        )
        assert params["organism"] == "MED4"
        assert "toLower($organism)" in cypher

    def test_invalid_ontology_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_genes_by_ontology_summary(ontology="bad", term_ids=["x"])

    def test_pfam_parent_label(self):
        cypher, _ = build_genes_by_ontology_summary(
            ontology="pfam", term_ids=["PF00001"],
        )
        assert "Pfam" in cypher
        assert "PfamClan" in cypher

    def test_tid_survives_with_distinct(self):
        """UNWIND-based summary query must carry tid through WITH DISTINCT."""
        cypher, _ = build_genes_by_ontology_summary(
            ontology="go_bp", term_ids=["go:0006260"],
        )
        for line in cypher.split("\n"):
            if "WITH DISTINCT" in line and "descendant" in line:
                assert "tid" in line, f"tid dropped from scope: {line}"

    @pytest.mark.parametrize("ontology", [
        "go_bp", "go_mf", "go_cc", "kegg", "ec",
        "cog_category", "cyanorak_role", "tigr_role", "pfam",
    ])
    def test_tid_survives_all_ontologies(self, ontology):
        """tid scoping must work for all ontology types (hierarchy + flat)."""
        cypher, _ = build_genes_by_ontology_summary(
            ontology=ontology, term_ids=["test:001"],
        )
        for line in cypher.split("\n"):
            if "WITH DISTINCT" in line and "descendant" in line:
                assert "tid" in line, (
                    f"{ontology}: tid dropped from scope: {line}"
                )


class TestBuildGeneOntologyTerms:
    def test_single_ontology_returns_expected_columns(self):
        """go_bp returns locus_tag, term_id, term_name in RETURN."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
        )
        assert "locus_tag" in cypher
        assert "term_id" in cypher
        assert "term_name" in cypher

    def test_leaf_filter_hierarchical(self):
        """go_bp has hierarchy_rels, so NOT EXISTS clause is present."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
        )
        assert "NOT EXISTS" in cypher
        assert "Biological_process_is_a_biological_process" in cypher
        assert "Biological_process_part_of_biological_process" in cypher

    def test_leaf_filter_flat_ontology(self):
        """cog_category is flat (no hierarchy_rels), so NO NOT EXISTS clause."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="cog_category",
        )
        assert "NOT EXISTS" not in cypher
        assert "CogFunctionalCategory" in cypher

    def test_leaf_filter_pfam(self):
        """pfam has cross-label hierarchy (parent_label), so NO NOT EXISTS."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="pfam",
        )
        assert "NOT EXISTS" not in cypher
        assert "Pfam" in cypher

    def test_leaf_filter_kegg(self):
        """kegg has gene_connects_to_level, so NO NOT EXISTS."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="kegg",
        )
        assert "NOT EXISTS" not in cypher
        assert "KeggTerm" in cypher

    def test_verbose_false(self):
        """Compact mode does not include organism_name in RETURN."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", verbose=False,
        )
        assert "organism_name" not in cypher

    def test_verbose_true(self):
        """Verbose mode includes organism_name in RETURN."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", verbose=True,
        )
        assert "organism_name" in cypher

    def test_limit_clause(self):
        """LIMIT is added when limit is provided."""
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", limit=10,
        )
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10

    def test_limit_none(self):
        """No LIMIT when limit is None."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp", limit=None,
        )
        assert "LIMIT" not in cypher

    def test_order_by(self):
        """Results are ordered by locus_tag then term id."""
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
        )
        assert "ORDER BY g.locus_tag, t.id" in cypher

    def test_invalid_ontology_raises(self):
        """Invalid ontology raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_gene_ontology_terms(locus_tags=["x"], ontology="bad")

    def test_params_include_locus_tags(self):
        """params dict has locus_tags key."""
        _, params = build_gene_ontology_terms(
            locus_tags=["PMM0001", "PMM0002"], ontology="go_bp",
        )
        assert params["locus_tags"] == ["PMM0001", "PMM0002"]


class TestBuildGeneOntologyTermsSummary:
    def test_returns_cypher_and_params(self):
        """Basic call returns cypher and params."""
        cypher, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="go_bp",
        )
        assert "gene_count" in cypher
        assert "term_count" in cypher
        assert "by_term" in cypher
        assert "gene_term_counts" in cypher

    def test_params_include_locus_tags(self):
        """params dict has locus_tags key."""
        _, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001", "PMM0002"], ontology="go_bp",
        )
        assert params["locus_tags"] == ["PMM0001", "PMM0002"]

    def test_invalid_ontology_raises(self):
        """Invalid ontology raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_gene_ontology_terms_summary(locus_tags=["x"], ontology="bad")


class TestBuildGeneExistenceCheck:
    def test_returns_cypher(self):
        """Cypher uses OPTIONAL MATCH pattern."""
        cypher, _ = build_gene_existence_check()
        assert "OPTIONAL MATCH" in cypher
        assert "lt" in cypher
        assert "found" in cypher

    def test_empty_params(self):
        """params dict is empty (locus_tags passed at execute time)."""
        _, params = build_gene_existence_check()
        assert params == {}


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


class TestBuildListExperiments:
    def test_no_filters(self):
        """No filters produces MATCH with no WHERE, no fulltext CALL."""
        cypher, params = build_list_experiments()
        assert "MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)" in cypher
        assert "WHERE" not in cypher
        assert "fulltext" not in cypher
        assert params == {}

    def test_organism_filter(self):
        """Organism filter uses ALL(word IN split) on organism_name OR coculture_partner."""
        cypher, params = build_list_experiments(organism="MED4")
        assert "ALL(word IN split(toLower($org)" in cypher
        assert "toLower(e.organism_name) CONTAINS word" in cypher
        assert "toLower(e.coculture_partner) CONTAINS word" in cypher
        assert params["org"] == "MED4"

    def test_treatment_type_filter(self):
        """Treatment type filter uses toLower IN with list param."""
        cypher, params = build_list_experiments(treatment_type=["coculture", "nitrogen_stress"])
        assert "toLower(e.treatment_type) IN $treatment_types" in cypher
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
        assert params["org"] == "MED4"
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
        assert "ALL(word IN split(toLower($org)" in cypher
        assert params["org"] == "MED4"

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
        """Same filter logic as detail builder — treatment_type list works."""
        cypher, params = build_list_experiments_summary(
            treatment_type=["coculture", "nitrogen_stress"]
        )
        assert "toLower(e.treatment_type) IN $treatment_types" in cypher
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


# ---------------------------------------------------------------------------
# Organism pre-validation builders
# ---------------------------------------------------------------------------


class TestBuildResolveOrganismForOrganism:
    def test_basic(self):
        cypher, params = build_resolve_organism_for_organism(organism="MED4")
        assert "Changes_expression_of" in cypher
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
        assert 'r.expression_status = "significant_up"' in cypher

    def test_direction_down(self):
        cypher, _ = build_differential_expression_by_gene_summary_global(
            direction="down"
        )
        assert 'r.expression_status = "significant_down"' in cypher

    def test_significant_only(self):
        cypher, _ = build_differential_expression_by_gene_summary_global(
            significant_only=True
        )
        assert 'r.expression_status <> "not_significant"' in cypher

    def test_direction_overrides_significant_only(self):
        cypher, _ = build_differential_expression_by_gene_summary_global(
            direction="up", significant_only=True
        )
        assert 'r.expression_status = "significant_up"' in cypher
        # The <> "not_significant" appears in CASE expressions (for median/max),
        # but should NOT appear in the WHERE clause when direction is set.
        where_part = cypher.split("RETURN")[0]
        assert 'r.expression_status <> "not_significant"' not in where_part

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
        assert 'r.expression_status = "significant_up"' in cypher
        assert "product" in cypher


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


class TestBuildDifferentialExpressionByOrthologSummaryGlobal:
    """Tests for build_differential_expression_by_ortholog_summary_global."""

    def test_single_group(self):
        cypher, params = build_differential_expression_by_ortholog_summary_global(
            group_ids=["cyanorak:CK_00000570"],
        )
        assert "$group_ids" in cypher
        assert params["group_ids"] == ["cyanorak:CK_00000570"]

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
        assert 'r.expression_status = "significant_up"' in cypher

    def test_significant_only(self):
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["cyanorak:CK_00000570"],
            significant_only=True,
        )
        assert 'r.expression_status <> "not_significant"' in cypher

    def test_direction_takes_precedence(self):
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["g1"], direction="down", significant_only=True,
        )
        assert 'r.expression_status = "significant_down"' in cypher
        # Direction takes precedence: significant_only's WHERE clause is NOT added
        assert 'r.expression_status <> "not_significant"' not in cypher

    def test_returns_expected_keys(self):
        cypher, _ = build_differential_expression_by_ortholog_summary_global(
            group_ids=["g1"],
        )
        for key in ["total_matching", "matching_genes", "matching_groups",
                     "experiment_count", "by_organism", "rows_by_status",
                     "rows_by_treatment_type", "by_table_scope",
                     "sig_log2fcs", "not_found_groups", "not_matched_groups"]:
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
        assert 'r.expression_status = "significant_up"' in cypher


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
        assert 'r.expression_status = "significant_up"' in cypher

    def test_significant_only_forwarded_to_diagnostics(self):
        """significant_only filter must appear in diagnostic Cypher."""
        result = build_differential_expression_by_ortholog_diagnostics(
            group_ids=["g1"], experiment_ids=["EXP001"],
            significant_only=True,
        )
        assert result is not None
        cypher, _ = result[0]
        assert 'r.expression_status <> "not_significant"' in cypher
