"""Unit tests for query builder functions — no Neo4j needed.

Verifies Cypher structure and parameter correctness.
"""

import pytest

from multiomics_explorer.kg.queries_lib import (
    ONTOLOGY_CONFIG,
    build_gene_ontology_terms,
    build_gene_overview,
    build_gene_stub,
    build_genes_by_ontology,
    build_get_gene_details,
    build_get_homologs_groups,
    build_get_homologs_members,
    build_list_gene_categories,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_resolve_gene,
    build_search_genes,
    build_search_ontology,
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
        assert "toLower(g.organism_strain)" in cypher

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
        for col in ["locus_tag", "gene_name", "product", "organism_strain"]:
            assert col in cypher

    def test_matches_all_identifiers(self):
        """Query checks all_identifiers list for alternate IDs (old locus tags, RefSeq IDs)."""
        cypher, _ = build_resolve_gene(identifier="x")
        assert "$identifier IN g.all_identifiers" in cypher

    def test_order_by_locus_tag(self):
        cypher, _ = build_resolve_gene(identifier="x")
        assert "ORDER BY g.locus_tag" in cypher


class TestBuildSearchGenes:
    def test_basic(self):
        cypher, params = build_search_genes(search_text="DNA repair")
        assert "fulltext" in cypher.lower() or "geneFullText" in cypher
        assert params["search_text"] == "DNA repair"

    def test_min_quality(self):
        _, params = build_search_genes(search_text="x", min_quality=2)
        assert params["min_quality"] == 2

    def test_organism_case_insensitive(self):
        """Organism filter uses toLower for case-insensitive matching."""
        cypher, params = build_search_genes(search_text="x", organism="prochlorococcus")
        assert params["organism"] == "prochlorococcus"
        assert "toLower($organism)" in cypher

    def test_organism_multi_word(self):
        """Multi-word organism uses ALL/split for word matching."""
        cypher, _ = build_search_genes(search_text="x", organism="Alteromonas EZ55")
        assert "ALL(word IN split(" in cypher

    def test_gene_summary_in_return(self):
        """RETURN clause includes gene_summary."""
        cypher, _ = build_search_genes(search_text="x")
        assert "gene_summary" in cypher

    def test_no_removed_properties(self):
        """RETURN clause should not reference removed gene properties."""
        cypher, _ = build_search_genes(search_text="x")
        assert "cluster_number" not in cypher
        assert "alteromonadaceae_og" not in cypher

    def test_category_param_when_provided(self):
        """When category is provided, it is passed as $category parameter."""
        cypher, params = build_search_genes(search_text="x", category="Photosynthesis")
        assert params["category"] == "Photosynthesis"
        assert "gene_category" in cypher
        assert "$category" in cypher

    def test_category_is_null_when_none(self):
        """When category is None, $category IS NULL allows all rows through."""
        cypher, params = build_search_genes(search_text="x", category=None)
        assert params["category"] is None
        assert "$category IS NULL" in cypher



class TestBuildGeneOverview:
    def test_gene_overview_query(self):
        """UNWIND present, returns all 12 expected columns, $gene_ids in params."""
        cypher, params = build_gene_overview(gene_ids=["PMM1428"])
        assert "UNWIND" in cypher
        assert params["locus_tags"] == ["PMM1428"]

    def test_gene_overview_columns(self):
        """Verify all column names in RETURN clause."""
        cypher, _ = build_gene_overview(gene_ids=["PMM1428"])
        expected_columns = [
            "locus_tag", "gene_name", "product", "gene_summary", "gene_category",
            "annotation_quality", "organism_strain", "annotation_types",
            "expression_edge_count", "significant_expression_count",
            "closest_ortholog_group_size", "closest_ortholog_genera",
        ]
        for col in expected_columns:
            assert col in cypher, f"Missing column '{col}' in RETURN clause"


class TestBuildGetGeneDetails:
    def test_get_gene_details_simplified(self):
        """g {.*} in RETURN, no nested sub-object traversals."""
        cypher, params = build_get_gene_details(gene_id="PMM0001")
        assert params["gene_id"] == "PMM0001"
        assert "g {.*}" in cypher
        assert "Gene_encodes_protein" not in cypher
        assert "Gene_belongs_to_organism" not in cypher
        assert "Gene_in_ortholog_group" not in cypher

    def test_build_get_gene_details_homologs_deleted(self):
        """build_get_gene_details_homologs no longer importable from queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_get_gene_details_homologs")


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


class TestBuildGeneStub:
    def test_returns_expected_columns(self):
        cypher, params = build_gene_stub(gene_id="PMM0001")
        assert params["lt"] == "PMM0001"
        for col in ["locus_tag", "gene_name", "product", "organism_strain"]:
            assert col in cypher

    def test_matches_by_locus_tag(self):
        cypher, _ = build_gene_stub(gene_id="PMM0001")
        assert "locus_tag: $lt" in cypher


class TestBuildGetHomologsGroups:
    def test_returns_og_enrichment_properties(self):
        cypher, params = build_get_homologs_groups(gene_id="PMM0845")
        assert params["lt"] == "PMM0845"
        for col in [
            "consensus_product", "consensus_gene_name",
            "member_count", "organism_count",
            "genera", "has_cross_genus_members",
        ]:
            assert col in cypher

    def test_orders_by_specificity_rank_source(self):
        cypher, _ = build_get_homologs_groups(gene_id="x")
        assert "ORDER BY og.specificity_rank, og.source" in cypher

    def test_source_filter(self):
        cypher, params = build_get_homologs_groups(gene_id="x", source="cyanorak")
        assert "og.source = $source" in cypher
        assert params["source"] == "cyanorak"

    def test_taxonomic_level_filter(self):
        cypher, params = build_get_homologs_groups(gene_id="x", taxonomic_level="Bacteria")
        assert "og.taxonomic_level = $level" in cypher
        assert params["level"] == "Bacteria"

    def test_max_specificity_rank_filter(self):
        cypher, params = build_get_homologs_groups(gene_id="x", max_specificity_rank=1)
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["max_rank"] == 1

    def test_no_filter_when_all_none(self):
        cypher, params = build_get_homologs_groups(gene_id="x")
        assert "WHERE" not in cypher
        assert params == {"lt": "x"}

    def test_gene_in_ortholog_group(self):
        cypher, _ = build_get_homologs_groups(gene_id="x")
        assert "Gene_in_ortholog_group" in cypher
        assert "OrthologGroup" in cypher

    def test_source_and_taxonomic_level_combined(self):
        """Both source and taxonomic_level filters appear in WHERE."""
        cypher, params = build_get_homologs_groups(
            gene_id="x", source="cyanorak", taxonomic_level="curated",
        )
        assert "og.source = $source" in cypher
        assert "og.taxonomic_level = $level" in cypher
        assert params["source"] == "cyanorak"
        assert params["level"] == "curated"

    def test_source_and_max_specificity_rank_combined(self):
        """Both source and max_specificity_rank filters appear in WHERE."""
        cypher, params = build_get_homologs_groups(
            gene_id="x", source="eggnog", max_specificity_rank=2,
        )
        assert "og.source = $source" in cypher
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["source"] == "eggnog"
        assert params["max_rank"] == 2

    def test_all_three_filters_combined(self):
        """All three filters (source, taxonomic_level, max_specificity_rank) in WHERE."""
        cypher, params = build_get_homologs_groups(
            gene_id="x", source="eggnog", taxonomic_level="Bacteria",
            max_specificity_rank=3,
        )
        assert "og.source = $source" in cypher
        assert "og.taxonomic_level = $level" in cypher
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params == {"lt": "x", "source": "eggnog", "level": "Bacteria", "max_rank": 3}

    @pytest.mark.parametrize("rank", [0, 1, 2, 3])
    def test_max_specificity_rank_boundary_values(self, rank):
        """Each valid rank value (0-3) produces correct WHERE clause."""
        cypher, params = build_get_homologs_groups(gene_id="x", max_specificity_rank=rank)
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["max_rank"] == rank


class TestBuildGetHomologsMembers:
    def test_includes_other_neq_g(self):
        cypher, _ = build_get_homologs_members(gene_id="x")
        assert "other <> g" in cypher

    def test_exclude_paralogs_true_adds_organism_filter(self):
        cypher, _ = build_get_homologs_members(gene_id="x", exclude_paralogs=True)
        assert "other.organism_strain <> g.organism_strain" in cypher

    def test_exclude_paralogs_false_omits_organism_filter(self):
        cypher, _ = build_get_homologs_members(gene_id="x", exclude_paralogs=False)
        assert "other.organism_strain <> g.organism_strain" not in cypher

    def test_returns_expected_columns(self):
        cypher, _ = build_get_homologs_members(gene_id="x")
        for col in ["og_name", "locus_tag", "gene_name", "product", "organism_strain"]:
            assert col in cypher

    def test_orders_correctly(self):
        cypher, _ = build_get_homologs_members(gene_id="x")
        assert "ORDER BY og.specificity_rank, og.source, other.organism_strain, other.locus_tag" in cypher

    def test_source_filter(self):
        cypher, params = build_get_homologs_members(gene_id="x", source="eggnog")
        assert "og.source = $source" in cypher
        assert params["source"] == "eggnog"

    def test_taxonomic_level_filter(self):
        cypher, params = build_get_homologs_members(gene_id="x", taxonomic_level="Cyanobacteria")
        assert "og.taxonomic_level = $level" in cypher
        assert params["level"] == "Cyanobacteria"

    def test_max_specificity_rank_filter(self):
        cypher, params = build_get_homologs_members(gene_id="x", max_specificity_rank=2)
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["max_rank"] == 2

    def test_source_and_taxonomic_level_combined(self):
        """Both source and taxonomic_level filters appear in WHERE."""
        cypher, params = build_get_homologs_members(
            gene_id="x", source="cyanorak", taxonomic_level="curated",
        )
        assert "og.source = $source" in cypher
        assert "og.taxonomic_level = $level" in cypher

    def test_all_filters_combined_with_exclude_paralogs(self):
        """All filters plus exclude_paralogs=True all appear in WHERE."""
        cypher, params = build_get_homologs_members(
            gene_id="x", source="eggnog", taxonomic_level="Bacteria",
            max_specificity_rank=3, exclude_paralogs=True,
        )
        assert "og.source = $source" in cypher
        assert "og.taxonomic_level = $level" in cypher
        assert "og.specificity_rank <= $max_rank" in cypher
        assert "other.organism_strain <> g.organism_strain" in cypher
        assert "other <> g" in cypher

    @pytest.mark.parametrize("rank", [0, 1, 2, 3])
    def test_max_specificity_rank_boundary_values(self, rank):
        """Each valid rank value (0-3) produces correct WHERE clause."""
        cypher, params = build_get_homologs_members(gene_id="x", max_specificity_rank=rank)
        assert "og.specificity_rank <= $max_rank" in cypher
        assert params["max_rank"] == rank


class TestBuildGetHomologsOldRemoved:
    def test_old_build_get_homologs_no_longer_exists(self):
        """Old build_get_homologs function should not exist in queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_get_homologs")

    def test_old_build_homolog_expression_no_longer_exists(self):
        """Old build_homolog_expression function should not exist in queries_lib."""
        import multiomics_explorer.kg.queries_lib as ql
        assert not hasattr(ql, "build_homolog_expression")


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
        # search_text should NOT be interpolated into cypher
        assert "replication" not in cypher

    def test_go_mf_uses_correct_index(self):
        cypher, _ = build_search_ontology(ontology="go_mf", search_text="binding")
        assert "'molecularFunctionFullText'" in cypher

    def test_go_cc_uses_correct_index(self):
        cypher, _ = build_search_ontology(ontology="go_cc", search_text="membrane")
        assert "'cellularComponentFullText'" in cypher

    def test_pfam_union_query(self):
        """Pfam search generates UNION query across both pfam and pfamClan indexes."""
        cypher, _ = build_search_ontology(ontology="pfam", search_text="polymerase")
        assert "CALL {" in cypher
        assert "UNION ALL" in cypher
        assert "'pfamFullText'" in cypher
        assert "'pfamClanFullText'" in cypher

    def test_non_pfam_no_union(self):
        """Non-pfam ontologies do not generate UNION queries."""
        for ontology in ["go_bp", "go_mf", "go_cc", "ec", "kegg",
                         "cog_category", "cyanorak_role", "tigr_role"]:
            cypher, _ = build_search_ontology(ontology=ontology, search_text="test")
            assert "UNION ALL" not in cypher, f"{ontology} should not have UNION"


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
        for col in ["locus_tag", "gene_name", "product", "organism_strain"]:
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


class TestBuildGeneOntologyTerms:
    @pytest.mark.parametrize("ontology,expected_label,expected_rel", [
        ("go_bp", "BiologicalProcess", "Gene_involved_in_biological_process"),
        ("go_mf", "MolecularFunction", "Gene_enables_molecular_function"),
        ("go_cc", "CellularComponent", "Gene_located_in_cellular_component"),
        ("ec", "EcNumber", "Gene_catalyzes_ec_number"),
        ("kegg", "KeggTerm", "Gene_has_kegg_ko"),
        ("cog_category", "CogFunctionalCategory", "Gene_in_cog_category"),
        ("cyanorak_role", "CyanorakRole", "Gene_has_cyanorak_role"),
        ("tigr_role", "TigrRole", "Gene_has_tigr_role"),
        ("pfam", "Pfam", "Gene_has_pfam"),
    ])
    def test_correct_label_and_rel(self, ontology, expected_label, expected_rel):
        cypher, _ = build_gene_ontology_terms(ontology=ontology, gene_id="PMM0001")
        assert expected_label in cypher
        assert expected_rel in cypher

    def test_leaf_only_adds_not_exists(self):
        cypher, _ = build_gene_ontology_terms(
            ontology="go_bp", gene_id="PMM0001", leaf_only=True,
        )
        assert "NOT EXISTS" in cypher
        # Hierarchy edges should be in the NOT EXISTS subquery
        assert "Biological_process_is_a_biological_process" in cypher
        assert "Biological_process_part_of_biological_process" in cypher

    def test_leaf_only_false_no_not_exists(self):
        cypher, _ = build_gene_ontology_terms(
            ontology="go_bp", gene_id="PMM0001", leaf_only=False,
        )
        assert "NOT EXISTS" not in cypher

    def test_returns_id_name_columns(self):
        for ontology in ["go_bp", "go_mf", "go_cc", "ec", "kegg"]:
            cypher, _ = build_gene_ontology_terms(ontology=ontology, gene_id="x")
            assert "t.id AS id" in cypher
            assert "t.name AS name" in cypher

    def test_invalid_ontology_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid ontology"):
            build_gene_ontology_terms(ontology="bad", gene_id="x")

    def test_go_mf_correct_label_and_rel(self):
        cypher, _ = build_gene_ontology_terms(ontology="go_mf", gene_id="PMM0001")
        assert "MolecularFunction" in cypher
        assert "Gene_enables_molecular_function" in cypher

    def test_go_cc_correct_label_and_rel(self):
        cypher, _ = build_gene_ontology_terms(ontology="go_cc", gene_id="PMM0001")
        assert "CellularComponent" in cypher
        assert "Gene_located_in_cellular_component" in cypher

    def test_leaf_only_ec(self):
        """leaf_only=True works for EC (only is_a hierarchy)."""
        cypher, _ = build_gene_ontology_terms(
            ontology="ec", gene_id="PMM0001", leaf_only=True,
        )
        assert "NOT EXISTS" in cypher
        assert "Ec_number_is_a_ec_number" in cypher

    def test_leaf_only_kegg(self):
        """leaf_only=True works for KEGG."""
        cypher, _ = build_gene_ontology_terms(
            ontology="kegg", gene_id="PMM0001", leaf_only=True,
        )
        assert "NOT EXISTS" in cypher
        assert "Kegg_term_is_a_kegg_term" in cypher

    def test_leaf_only_flat_ontology_returns_all(self):
        """Flat ontologies (empty hierarchy_rels) ignore leaf_only — all terms are leaves."""
        cypher, _ = build_gene_ontology_terms(
            ontology="cog_category", gene_id="PMM0001", leaf_only=True,
        )
        assert "NOT EXISTS" not in cypher
        assert "CogFunctionalCategory" in cypher
        assert "Gene_in_cog_category" in cypher

    def test_cyanorak_role_leaf_only(self):
        """CyanorakRole has hierarchy, so leaf_only=True uses NOT EXISTS."""
        cypher, _ = build_gene_ontology_terms(
            ontology="cyanorak_role", gene_id="PMM0001", leaf_only=True,
        )
        assert "NOT EXISTS" in cypher
        assert "Cyanorak_role_is_a_cyanorak_role" in cypher


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


