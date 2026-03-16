"""Unit tests for query builder functions — no Neo4j needed.

Verifies Cypher structure and parameter correctness.
"""

import pytest

from multiomics_explorer.kg.queries_lib import (
    ONTOLOGY_CONFIG,
    build_compare_conditions,
    build_gene_ontology_terms,
    build_genes_by_ontology,
    build_list_condition_types,
    build_list_gene_categories,
    build_list_organisms,
    build_search_genes,
    build_search_ontology,
    build_resolve_gene,
    build_get_gene_details_homologs,
    build_get_gene_details_main,
    build_get_homologs,
    build_homolog_expression,
    build_query_expression,
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

    def test_cluster_id_via_coalesce(self):
        """RETURN clause includes cluster_id via coalesce of cluster_number and alteromonadaceae_og."""
        cypher, _ = build_search_genes(search_text="x")
        assert "cluster_id" in cypher
        assert "coalesce" in cypher.lower()
        assert "cluster_number" in cypher
        assert "alteromonadaceae_og" in cypher

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

    def test_limit_parameter(self):
        _, params = build_search_genes(search_text="x", limit=5)
        assert params["limit"] == 5

    def test_default_limit(self):
        _, params = build_search_genes(search_text="x")
        assert "limit" in params


class TestBuildGetGeneDetails:
    def test_main_query(self):
        cypher, params = build_get_gene_details_main(gene_id="PMM0001")
        assert params["lt"] == "PMM0001"
        assert "Gene_encodes_protein" in cypher
        assert "Gene_belongs_to_organism" in cypher

    def test_homologs_query(self):
        cypher, params = build_get_gene_details_homologs(gene_id="PMM0001")
        assert params["lt"] == "PMM0001"
        assert "Gene_is_homolog_of_gene" in cypher


class TestBuildQueryExpression:
    def test_by_gene(self):
        cypher, params = build_query_expression(gene_id="PMM0845")
        assert params["gene_id"] == "PMM0845"
        assert "g.locus_tag = $gene_id" in cypher

    def test_direction_lowercased(self):
        _, params = build_query_expression(gene_id="x", direction="UP")
        assert params["dir"] == "up"

    def test_includes_orthologs(self):
        cypher, _ = build_query_expression(gene_id="x", include_orthologs=True)
        assert "ortholog" in cypher.lower()

    def test_excludes_orthologs_by_default(self):
        cypher, _ = build_query_expression(gene_id="x")
        assert "ortholog" not in cypher.lower()

    def test_min_log2fc(self):
        cypher, params = build_query_expression(gene_id="x", min_log2fc=1.5)
        assert params["min_fc"] == 1.5
        assert "abs(r.log2_fold_change) >= $min_fc" in cypher

    def test_max_pvalue(self):
        cypher, params = build_query_expression(gene_id="x", max_pvalue=0.05)
        assert params["max_pv"] == 0.05


class TestBuildCompareConditions:
    def test_by_gene_ids(self):
        cypher, params = build_compare_conditions(gene_ids=["PMM0001", "PMM0002"])
        assert params["gene_ids"] == ["PMM0001", "PMM0002"]
        assert "g.locus_tag IN $gene_ids" in cypher

    def test_by_organisms(self):
        cypher, params = build_compare_conditions(organisms=["MED4"])
        assert params["organisms"] == ["MED4"]


class TestBuildGetHomologs:
    def test_basic(self):
        cypher, params = build_get_homologs(gene_id="PMM0845")
        assert params["lt"] == "PMM0845"
        assert "Gene_is_homolog_of_gene" in cypher

    def test_returns_expected_columns(self):
        cypher, _ = build_get_homologs(gene_id="x")
        for col in ["locus_tag", "organism_strain", "distance"]:
            assert col in cypher


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


class TestBuildListConditionTypes:
    def test_cypher_structure(self):
        cypher, params = build_list_condition_types()
        assert "MATCH (e:EnvironmentalCondition)" in cypher
        assert "condition_type" in cypher
        assert "cnt" in cypher
        assert "ORDER BY cnt DESC" in cypher

    def test_no_params(self):
        _, params = build_list_condition_types()
        assert params == {}


class TestBuildListOrganisms:
    def test_cypher_structure(self):
        cypher, params = build_list_organisms()
        assert "MATCH (o:OrganismTaxon)" in cypher
        assert "OPTIONAL MATCH" in cypher
        assert "Gene_belongs_to_organism" in cypher

    def test_returns_expected_columns(self):
        cypher, _ = build_list_organisms()
        for col in ["name", "genus", "strain", "clade", "gene_count"]:
            assert col in cypher

    def test_no_params(self):
        _, params = build_list_organisms()
        assert params == {}

    def test_ordered_by_genus_and_name(self):
        cypher, _ = build_list_organisms()
        assert "ORDER BY o.genus, o.preferred_name" in cypher


class TestOntologyConfig:
    def test_all_five_keys_present(self):
        assert set(ONTOLOGY_CONFIG.keys()) == {"go_bp", "go_mf", "go_cc", "ec", "kegg"}

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


class TestBuildSearchOntology:
    @pytest.mark.parametrize("ontology,expected_index", [
        ("go_bp", "biologicalProcessFullText"),
        ("go_mf", "molecularFunctionFullText"),
        ("go_cc", "cellularComponentFullText"),
        ("ec", "ecNumberFullText"),
        ("kegg", "keggFullText"),
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

    def test_limit_parameter(self):
        _, params = build_search_ontology(ontology="ec", search_text="x", limit=10)
        assert params["limit"] == 10

    def test_go_mf_uses_correct_index(self):
        cypher, _ = build_search_ontology(ontology="go_mf", search_text="binding")
        assert "'molecularFunctionFullText'" in cypher

    def test_go_cc_uses_correct_index(self):
        cypher, _ = build_search_ontology(ontology="go_cc", search_text="membrane")
        assert "'cellularComponentFullText'" in cypher


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

    def test_limit_parameter(self):
        _, params = build_genes_by_ontology(
            ontology="go_bp", term_ids=["go:0006260"], limit=5,
        )
        assert params["limit"] == 5


class TestBuildGeneOntologyTerms:
    @pytest.mark.parametrize("ontology,expected_label,expected_rel", [
        ("go_bp", "BiologicalProcess", "Gene_involved_in_biological_process"),
        ("go_mf", "MolecularFunction", "Gene_enables_molecular_function"),
        ("go_cc", "CellularComponent", "Gene_located_in_cellular_component"),
        ("ec", "EcNumber", "Gene_catalyzes_ec_number"),
        ("kegg", "KeggTerm", "Gene_has_kegg_ko"),
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

    def test_limit_parameter(self):
        cypher, params = build_gene_ontology_terms(
            ontology="go_bp", gene_id="PMM0001", limit=20,
        )
        assert params["limit"] == 20
        assert "$limit" in cypher

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


class TestBuildHomologExpression:
    def test_basic(self):
        cypher, params = build_homolog_expression(gene_ids=["PMM0001", "PMM0002"])
        assert params["ids"] == ["PMM0001", "PMM0002"]
        assert "g.locus_tag IN $ids" in cypher
